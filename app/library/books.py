"""Permission-gated, resumable PDF parts with atomic whole-book activation."""

import json
import hashlib
import multiprocessing
import re
import uuid
import time
from contextlib import nullcontext
from typing import Any
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import Chunk, Collection, Document, LibraryBook
from app.embeddings.provider import provider
from app.ingestion.chunking import chunk_segments
from app.ingestion.loaders import ExtractedSegment
from app.ingestion.pipeline import enqueue, process_job
from app.library.catalog import atomic_json, digest
from app.library.source import fingerprint, verify_source


def preparation_folder(cache: Path, resource) -> Path:
    version = resource.get("preparation_version", 2)
    if version not in {2, 3}:
        raise ValueError("BOOK_PREPARATION_VERSION")
    revision = resource.get("preparation_revision", 0)
    if not isinstance(revision, int) or not 0 <= revision <= 100:
        raise ValueError("BOOK_PREPARATION_REVISION")
    suffix = f"-r{revision}" if revision else ""
    return cache / resource["id"] / resource["sha256"] / f"bookparts-v{version}{suffix}"


def preparation_identity(prepared):
    return hashlib.sha256(
        json.dumps(
            [(p["first_page"], p["last_page"], p["sha256"]) for p in prepared["parts"]]
        ).encode()
    ).hexdigest()


def non_text_preparation(resource, prepared):
    """A complete blank/decorative range needs an outcome, not fabricated chunks."""
    first, last = resource.get("page_range", [1, resource.get("pdf_pages", 0)])
    outcomes = prepared.get("blank_pages", []) + prepared.get("reviewed_non_text_pages", [])
    return bool(
        prepared.get("complete")
        and not prepared.get("parts")
        and not prepared.get("ocr_required_pages")
        and prepared.get("source_sha256") == resource["sha256"]
        and 1 <= first <= last
        and last - first < 2000
        and sorted(outcomes) == list(range(first, last + 1))
    )


def require_shared_permission(resource):
    """Shared and private approvals have disjoint uses and explicit scopes."""
    rights = resource["rights"]
    private = resource["access"]["visibility"] == "PRIVATE"
    use = "private_retrieval" if private else "shared_retrieval"
    if (
        rights.get("permission_status") != "APPROVED"
        or not {"local_index", use} <= set(rights.get("permitted_uses", []))
        or rights.get("approved_sha256") != resource["sha256"]
        or not rights.get("evidence")
        or resource["access"]["visibility"] not in {"PRIVATE", "CURATED_SHARED"}
    ):
        raise ValueError("SOURCE_PERMISSION_REQUIRED")
    if resource.get("presence") != "PRESENT" or resource["format"] not in {
        "pdf",
        "html",
        "htm",
        "md",
        "txt",
        "docx",
    }:
        raise ValueError("PRESENT_SUPPORTED_SOURCE_REQUIRED")
    uuid.UUID(resource["id"])
    if not re.fullmatch(r"[a-f0-9]{64}", resource["sha256"]):
        raise ValueError("SOURCE_CHECKSUM_INVALID")
    if private:
        uuid.UUID(resource["access"]["owner_id"])


def _prepare_pages(
    resource, folder: Path, limit: int, *, verified_stat=None, source_pdf=None, source_toc=None
):
    import pymupdf

    source = Path(resource["absolute_path"])
    if source.is_symlink() or source.stat().st_size > (
        2 * 1024**3 if resource.get("page_range") else 512 * 1024**2
    ):
        raise ValueError("BOOK_FILE_LIMIT")
    if verified_stat is None:
        verify_source(resource)
    elif fingerprint(source) != verified_stat:
        raise ValueError("SOURCE_CHANGED_DURING_PREPARATION")
    folder.mkdir(parents=True, exist_ok=True)
    state_path = folder / "preparation.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {
            "source_sha256": resource["sha256"],
            "next_page": resource.get("page_range", [1])[0],
            "parts": [],
            "blank_pages": [],
            "ocr_required_pages": [],
            "ocr_pages": [],
            "complete": False,
        }
    )
    assert state["source_sha256"] == resource["sha256"], "SOURCE_CHECKSUM_CHANGED"
    with nullcontext(source_pdf) if source_pdf is not None else pymupdf.open(source) as pdf:
        first_page, last_page = resource.get("page_range", [1, len(pdf)])
        if (
            pdf.needs_pass
            or not 1 <= first_page <= last_page <= len(pdf)
            or last_page - first_page + 1 > 2000
        ):
            raise ValueError("BOOK_PAGE_LIMIT_OR_ENCRYPTED")
        state["total_pdf_pages"] = last_page - first_page + 1
        state["source_total_pdf_pages"] = len(pdf)
        outlines = sorted(
            [
                (title.strip()[:500], page)
                for level, title, page in (
                    []
                    if resource.get("outline_level", 1) == 0
                    else source_toc
                    if source_toc is not None
                    else pdf.get_toc()
                )
                if level == resource.get("outline_level", 1)
                and title.strip()
                and title.strip().lower() != "blank page"
                and first_page <= page <= last_page
            ],
            key=lambda item: item[1],
        )
        # Only monotonic valid PDF outline destinations are accepted. Printed
        # page labels and guessed chapter names are never manufactured.
        if outlines != sorted(outlines, key=lambda item: item[1]):
            outlines = []
        pages: list[dict[str, Any]] = []
        chunk_count = 0
        metadata = {
            "book_id": resource["id"],
            "source_sha256": resource["sha256"],
            "edition": resource.get("edition"),
            "extraction": "PDF_EMBEDDED_TEXT",
            "formula_review_required": True,
            "source_notice": resource.get("source_notice"),
        }
        pages = state.pop("pending_pages", [])
        chunk_count = sum(
            len(
                list(
                    chunk_segments(
                        [
                            ExtractedSegment(
                                item["text"],
                                heading_path=item.get("chapter"),
                                page_start=item["page"],
                                page_end=item["page"],
                                metadata=metadata,
                            )
                        ]
                    )
                )
            )
            for item in pages
        )

        def flush():
            nonlocal pages, chunk_count
            if not pages:
                return
            path = folder / f"part-{pages[0]['page']:04d}-{pages[-1]['page']:04d}.bookpart"
            atomic_json(path, {"format": "oscar-bookpart-v1", "pages": pages, "metadata": metadata})
            state["parts"].append(
                {
                    "path": str(path),
                    "sha256": digest(path),
                    "first_page": pages[0]["page"],
                    "last_page": pages[-1]["page"],
                    "expected_chunks": chunk_count,
                }
            )
            pages, chunk_count = [], 0

        start = state["next_page"]
        for number in range(start, min(last_page + 1, start + limit)):
            if (
                resource.get("physical_page_buckets")
                and pages
                and (number - first_page) // 8 != (pages[0]["page"] - first_page) // 8
            ):
                flush()
            page = pdf[number - 1]
            review = resource.get("page_reviews", {}).get(str(number))
            if review and review.get("source_sha256") != resource["sha256"]:
                raise ValueError("PAGE_REVIEW_CHECKSUM_CHANGED")
            if review and review["classification"] == "NON_TEXT_DECORATION":
                state.setdefault("reviewed_non_text_pages", []).append(number)
                state["next_page"] = number + 1
                continue
            if page.rect.width * page.rect.height * (150 / 72) ** 2 > 12_000_000:
                raise ValueError("BOOK_PAGE_RENDER_LIMIT")
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", page.get_text())
            if review and review.get("text"):
                text = review["text"]
            ocr = False
            if len(re.sub(r"\W", "", text)) < 20 and not review and resource.get("ocr_tessdata"):
                ocr_text = page.get_text(
                    textpage=page.get_textpage_ocr(
                        language="eng", dpi=150, full=True, tessdata=resource["ocr_tessdata"]
                    )
                )
                if ocr_text.strip():
                    text = ocr_text
                    ocr = True
                    state.setdefault("ocr_pages", []).append(number)
            if len(text) > 100000:
                raise ValueError("BOOK_PAGE_TEXT_LIMIT")
            if not text.strip():
                preview = page.get_pixmap(
                    matrix=pymupdf.Matrix(0.25, 0.25), colorspace=pymupdf.csGRAY, alpha=False
                )
                ink = sum(value < 245 for value in preview.samples) / max(1, len(preview.samples))
                if ink < 0.00005:
                    state["blank_pages"].append(number)
                else:
                    state["ocr_required_pages"].append(number)
            else:
                chapter = next((title for title, p in reversed(outlines) if p <= number), None)
                count = len(
                    list(
                        chunk_segments(
                            [
                                ExtractedSegment(
                                    text,
                                    heading_path=chapter,
                                    page_start=number,
                                    page_end=number,
                                    metadata=metadata,
                                )
                            ]
                        )
                    )
                )
                if count > 200:
                    raise ValueError("BOOK_PAGE_CHUNK_LIMIT")
                if len(pages) >= 8 or chunk_count + count > 200:
                    flush()
                pages.append(
                    {
                        "page": number,
                        "text": text,
                        "chapter": chapter,
                        "metadata": {
                            "extraction": review.get(
                                "extraction", "VISUALLY_REVIEWED_TRANSCRIPTION"
                            )
                            if review
                            else "LOCAL_TESSERACT_OCR"
                            if ocr
                            else "PDF_EMBEDDED_TEXT"
                        },
                    }
                )
                chunk_count += count
            state["next_page"] = number + 1
        state["complete"] = state["next_page"] > last_page
        if state["complete"]:
            flush()
        else:
            state["pending_pages"] = pages
        atomic_json(state_path, state)
    return state


def _prepare_child(resource, folder, limit, sender, verified_stat=None, whole_book=False):
    try:
        if resource["format"] == "pdf" and whole_book:
            import pymupdf

            with pymupdf.open(resource["absolute_path"]) as pdf:
                toc = [] if resource.get("outline_level", 1) == 0 else pdf.get_toc()
                while True:
                    state = _prepare_pages(
                        resource,
                        Path(folder),
                        limit,
                        verified_stat=verified_stat,
                        source_pdf=pdf,
                        source_toc=toc,
                    )
                    if state["complete"]:
                        break
                    sender.send(("progress", state["next_page"]))
        else:
            state = (
                _prepare_pages(resource, Path(folder), limit, verified_stat=verified_stat)
                if resource["format"] == "pdf"
                else _prepare_text(resource, Path(folder))
            )
        sender.send((True, state))
    except Exception as exc:
        code = str(exc) if re.fullmatch(r"[A-Z_]+", str(exc)) else "BOOK_PREPARATION_FAILED"
        sender.send((False, code))
    finally:
        sender.close()


def _prepare_text(resource, folder: Path):
    from app.config import Settings
    from app.ingestion.loaders import load

    source = Path(resource["absolute_path"])
    if digest(source) != resource["sha256"]:
        raise ValueError("SOURCE_CHECKSUM_CHANGED")
    segments = list(
        chunk_segments(
            load(
                source,
                Settings(
                    embedding_provider="disabled",
                    embedding_dimensions=1536,
                    max_extract_chars=5_000_000,
                ),
            )
        )
    )
    if not segments:
        raise ValueError("EMPTY_SOURCE")
    folder.mkdir(parents=True, exist_ok=True)
    state = {
        "source_sha256": resource["sha256"],
        "next_page": None,
        "parts": [],
        "blank_pages": [],
        "ocr_required_pages": [],
        "ocr_pages": [],
        "complete": True,
        "total_pdf_pages": None,
    }
    metadata = {
        "book_id": resource["id"],
        "source_sha256": resource["sha256"],
        "edition": resource.get("edition"),
        "extraction": "STRUCTURED_TEXT",
        "source_notice": resource.get("source_notice"),
    }
    for start in range(0, len(segments), 8):
        selected = segments[start : start + 8]
        path = folder / f"part-{start:05d}.bookpart"
        atomic_json(
            path,
            {
                "format": "oscar-bookpart-v1",
                "metadata": metadata,
                "pages": [
                    {"page": None, "text": s.text, "chapter": s.heading_path} for s in selected
                ],
            },
        )
        count = len(
            list(
                chunk_segments(
                    load(path, Settings(embedding_provider="disabled", embedding_dimensions=1536))
                )
            )
        )
        state["parts"].append(
            {
                "path": str(path),
                "sha256": digest(path),
                "first_page": start,
                "last_page": start + len(selected) - 1,
                "expected_chunks": count,
            }
        )
    atomic_json(folder / "preparation.json", state)
    return state


def prepare(
    resource, cache: Path, *, page_batch=40, timeout=120, memory_bytes=None, whole_book=False
):
    require_shared_permission(resource)
    source_path = Path(resource["absolute_path"])
    if source_path.is_symlink() or source_path.stat().st_size > (
        2 * 1024**3 if resource.get("page_range") else 512 * 1024**2
    ):
        raise ValueError("BOOK_FILE_LIMIT")
    if memory_bytes is None:
        memory_bytes = (
            2 * 1024**3
            if resource.get("page_range")
            and Path(resource["absolute_path"]).stat().st_size > 512 * 1024**2
            else 512 * 1024**2
        )
    if not 0 < memory_bytes <= 2 * 1024**3:
        raise ValueError("BOOK_PREPARATION_MEMORY_BUDGET")
    if not 1 <= page_batch <= 100:
        raise ValueError("BOOK_PAGE_BATCH_LIMIT")
    folder = preparation_folder(cache, resource)
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    verified_stat = verify_source(resource)
    process = ctx.Process(
        target=_prepare_child,
        args=(resource, str(folder), page_batch, sender, verified_stat, whole_book),
    )
    process.start()
    assert process.pid is not None
    sender.close()
    try:
        from app.library.limits import resident_bytes

        deadline = time.monotonic() + timeout
        previous_page = 0
        progress_updates = 0
        while True:
            if resident_bytes(process.pid) > memory_bytes:
                raise ValueError("BOOK_PREPARATION_MEMORY_LIMIT")
            if receiver.poll(0.2):
                ok, result = receiver.recv()
                if ok == "progress":
                    progress_updates += 1
                    if (
                        not whole_book
                        or not isinstance(result, int)
                        or result <= previous_page
                        or progress_updates > 2000 // page_batch + 1
                    ):
                        raise ValueError("BOOK_PREPARATION_PROGRESS_INVALID")
                    previous_page = result
                    deadline = time.monotonic() + timeout
                    continue
                if not ok:
                    raise ValueError(result)
                return result
            if time.monotonic() > deadline:
                raise ValueError("BOOK_PREPARATION_TIMEOUT")
            if not process.is_alive():
                raise ValueError("BOOK_PREPARATION_CHILD_EXITED")
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        receiver.close()


def ingest_parts(
    db, resource, prepared, collection: str, settings, *, limit=10, allow_partial=False
):
    """Resume part jobs; readers see old generation until every new part is ready."""
    require_shared_permission(resource)
    if resource.get("collection") and resource["collection"] != collection:
        raise ValueError("SOURCE_COLLECTION_SCOPE_MISMATCH")
    if not prepared["complete"]:
        raise ValueError("BOOK_PREPARATION_INCOMPLETE")
    if prepared["ocr_required_pages"] and not allow_partial:
        raise ValueError("BOOK_OCR_REVIEW_REQUIRED")
    if not prepared["parts"] or prepared["source_sha256"] != resource["sha256"]:
        raise ValueError("BOOK_PREPARATION_INVALID")
    verify_source(resource)
    if settings.embedding_provider not in {"disabled", "ollama"}:
        raise ValueError("LOCAL_BOOK_EMBEDDINGS_REQUIRED")
    col = db.scalar(select(Collection).where(Collection.slug == collection))
    visibility = resource["access"]["visibility"]
    if col is None and visibility == "PRIVATE" and collection in settings.private_collections:
        col = Collection(
            slug=collection, title=collection.replace("-", " ").title(), visibility="PRIVATE"
        )
        db.add(col)
        db.commit()
    permitted = (
        settings.private_collections if visibility == "PRIVATE" else settings.allowed_collections
    )
    if not col or col.visibility != visibility or collection not in permitted:
        raise ValueError("COLLECTION_SCOPE_REQUIRED")
    owner = uuid.UUID(resource["access"]["owner_id"]) if visibility == "PRIVATE" else None
    desired_author = ", ".join(resource["authors"])[:300] or None
    book_id = uuid.UUID(resource["id"])
    # Session advisory lock serializes aggregate activation, even though the
    # existing ingestion pipeline commits individual durable jobs.
    lock_key = int.from_bytes(book_id.bytes[:8], "big", signed=True)
    from sqlalchemy import text

    lock_connection = db.get_bind().engine.connect()
    if not lock_connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}):
        lock_connection.close()
        raise ValueError("BOOK_BUSY")
    try:
        book = db.get(LibraryBook, book_id, populate_existing=True)
        if not book:
            db.execute(select(Collection).where(Collection.id == col.id).with_for_update())
            book = db.get(LibraryBook, book_id, populate_existing=True)
        if not book:
            book = LibraryBook(
                id=book_id,
                collection_id=col.id,
                title=resource["title"],
                author=", ".join(resource["authors"])[:300] or None,
                edition=resource.get("edition"),
                approved=True,
                visibility=visibility,
                owner_id=owner,
            )
            db.add(book)
            db.commit()
        if (
            not book.approved
            or book.collection_id != col.id
            or book.visibility != visibility
            or book.owner_id != owner
        ):
            raise ValueError("BOOK_REVOKED_OR_SCOPE_CHANGED")
        embedder = provider(settings)
        identity = embedder.identity if embedder else None
        prepared_identity = preparation_identity(prepared)
        unchanged_preparation = (
            book.source_sha256 == resource["sha256"]
            and book.preparation_sha256 == prepared_identity
        )
        generation = book.active_generation if unchanged_preparation else book.active_generation + 1
        completed = 0
        expected_ids = []
        reused_ids = []
        processed = 0
        for part in prepared["parts"]:
            db.refresh(book)
            if not book.approved:
                raise ValueError("BOOK_REVOKED")
            key = f"book:{book.id}:{generation}:{part['first_page']}:{part['last_page']}"
            doc = db.scalar(
                select(Document).where(
                    Document.collection_id == col.id, Document.canonical_key == key
                )
            )
            if not doc and unchanged_preparation:
                doc = db.scalar(
                    select(Document).where(
                        Document.book_id == book.id,
                        Document.book_generation == book.active_generation,
                        Document.canonical_key.like(
                            f"book:{book.id}:%:{part['first_page']}:{part['last_page']}"
                        ),
                    )
                )
            if not doc and book.active_generation and not unchanged_preparation:
                prior = db.scalar(
                    select(Document).where(
                        Document.book_id == book.id,
                        Document.book_generation == book.active_generation,
                        Document.canonical_key.like(
                            f"book:{book.id}:%:{part['first_page']}:{part['last_page']}"
                        ),
                        Document.approved.is_(True),
                        Document.status != "DELETED",
                    )
                )
                if prior and prior.embedding_identity == identity:
                    from app.ingestion.loaders import load

                    current = list(chunk_segments(load(Path(part["path"]), settings)))
                    old = list(
                        db.scalars(
                            select(Chunk)
                            .where(
                                Chunk.document_id == prior.id,
                                Chunk.revision == prior.active_revision,
                            )
                            .order_by(Chunk.ordinal)
                        )
                    )

                    def signature(segment):
                        return (
                            segment.text,
                            segment.heading_path,
                            segment.page_start,
                            segment.page_end,
                        )

                    if (
                        len(current) == len(old)
                        and [signature(s) for s in current] == [signature(s) for s in old]
                        and all(
                            prior_chunk.source_metadata.get(field) == segment.metadata.get(field)
                            for prior_chunk, segment in zip(old, current, strict=True)
                            for field in [
                                "edition",
                                "extraction",
                                "formula_review_required",
                                "source_notice",
                            ]
                        )
                    ):
                        expected_ids.append(prior.id)
                        reused_ids.append(prior.id)
                        completed += 1
                        continue
            if doc and (doc.status == "DELETED" or not doc.approved):
                raise ValueError("BOOK_PART_REVOKED")
            if (
                doc
                and doc.active_revision > 0
                and (doc.content_sha256 == part["sha256"] or unchanged_preparation)
                and doc.embedding_identity == identity
            ):
                expected_ids.append(doc.id)
                completed += 1
                continue
            if unchanged_preparation:
                raise ValueError("BOOK_REEMBED_REQUIRED")
            if processed >= limit:
                continue
            if digest(Path(part["path"])) != part["sha256"]:
                raise ValueError("BOOKPART_CHECKSUM_CHANGED")
            job = enqueue(
                db,
                Path(part["path"]),
                collection,
                approved=True,
                canonical_key=key,
                title=resource["title"],
                author=desired_author,
                subject=resource["category"],
                book_id=str(book.id),
                book_generation=generation,
                license_type="USER_AUTHORIZED_PRIVATE"
                if visibility == "PRIVATE"
                else "CURATOR_REVIEWED",
                usage_notes=resource["rights"]["evidence"][:4000],
                source_url=resource.get("source_url"),
                content_type="." + resource["format"],
                publication_year=resource.get("publication_year"),
            )
            outcome = process_job(db, job.id, settings)
            processed += 1
            if outcome not in {"INDEXED", "UNCHANGED"}:
                return {
                    "status": "INDEX_FAILED",
                    "error_code": job.error_code or "BOOK_PART_FAILED",
                    "failed_job_id": str(job.id),
                    "completed_parts": completed,
                    "total_parts": len(prepared["parts"]),
                }
            expected_ids.append(job.document_id)
            completed += 1
        if completed == len(prepared["parts"]):
            count = db.scalar(
                select(func.count())
                .select_from(Chunk)
                .join(Document)
                .where(Document.id.in_(expected_ids), Chunk.revision == Document.active_revision)
            )
            if count != sum(p["expected_chunks"] for p in prepared["parts"]):
                raise ValueError("BOOK_CHUNK_COVERAGE_MISMATCH")
            verify_source(resource)
            db.refresh(book, with_for_update=True)
            if not book.approved or book.visibility != visibility or book.owner_id != owner:
                raise ValueError("BOOK_REVOKED")
            status = "PARTIALLY_INDEXED" if prepared["ocr_required_pages"] else "INDEXED"
            book.active_generation, book.source_sha256, book.status = (
                generation,
                resource["sha256"],
                status,
            )
            book.preparation_sha256 = prepared_identity
            book.title, book.author, book.edition = (
                resource["title"],
                desired_author,
                resource.get("edition"),
            )
            for expected_id in expected_ids:
                expected_doc = db.get(Document, expected_id)
                assert expected_doc is not None
                expected_doc.title, expected_doc.author = resource["title"], desired_author
                expected_doc.publication_year = resource.get("publication_year")
            for reused in reused_ids:
                reused_document = db.get(Document, reused)
                assert reused_document is not None
                reused_document.book_generation = generation
            db.commit()
            return {
                "status": status,
                "completed_parts": completed,
                "chunks": count,
                "total_pdf_pages": prepared["total_pdf_pages"],
                "blank_pages": prepared["blank_pages"],
                "generation": generation,
                "embedding_identity": identity,
                "reused_unchanged_parts": len(reused_ids),
            }
        return {
            "status": "PROCESSING",
            "completed_parts": completed,
            "total_parts": len(prepared["parts"]),
        }
    finally:
        db.rollback()
        try:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()
        finally:
            lock_connection.close()


def revoke_book(db, resource, settings):
    """Persist a deny tombstone even if a pending worker has not registered yet."""
    from sqlalchemy.exc import IntegrityError

    book_id = uuid.UUID(resource["id"])
    existing = db.get(LibraryBook, book_id)
    visibility = resource["access"]["visibility"]
    owner = resource["access"].get("owner_id")
    if not existing and visibility == "PRIVATE" and not owner:
        return  # An unapproved ownerless source cannot pass ingestion admission.
    slug = resource["collection"]
    col = (
        db.get(Collection, existing.collection_id)
        if existing
        else db.scalar(select(Collection).where(Collection.slug == slug))
    )
    if not col:
        allowed = (
            settings.private_collections
            if visibility == "PRIVATE"
            else settings.allowed_collections
        )
        if slug not in allowed:
            raise ValueError("COLLECTION_SCOPE_REQUIRED")
        col = Collection(slug=slug, title=slug.replace("-", " ").title(), visibility=visibility)
        db.add(col)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            col = db.scalar(select(Collection).where(Collection.slug == slug))
    assert col is not None
    db.execute(select(Collection).where(Collection.id == col.id).with_for_update())
    book = db.get(LibraryBook, book_id, populate_existing=True, with_for_update=True)
    if not book:
        book = LibraryBook(
            id=book_id,
            collection_id=col.id,
            title=resource["title"],
            visibility=visibility,
            owner_id=uuid.UUID(owner) if owner else None,
        )
        db.add(book)
    book.approved, book.status = False, "REVOKED"
    db.commit()
