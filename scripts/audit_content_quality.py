"""Content quality audit script for OSCAR local knowledge library.

Comprehensive audit covering:
1. Database chunks and documents (Unicode replacement characters, control chars, noise).
2. Current OCR pages for heuristic math, table and gibberish flags.
3. Visual review groups (12 exact-pixel groups) for classification fidelity.
4. Compilation attribution (159 ranges, 157 generic + 2 named).
5. Metadata & educational completeness (summaries vs full texts).

Outputs:
- D:/AI/OSCAR/Knowledge/Catalog/reports/quality-review/2026-10-26/quality-findings.jsonl
- D:/AI/OSCAR/Knowledge/Catalog/reports/quality-review/2026-10-26/quality-findings.csv
- D:/AI/OSCAR/Knowledge/Catalog/reports/quality-review/2026-10-26/REVIEW_COVERAGE.json
"""

import csv
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db.session import session
from app.library.catalog import read_catalog
from app.library.quality import classify_representation, screened_evidence_sql

CATALOG_DIR = Path("D:/AI/OSCAR/Knowledge/Catalog")
OUTPUT_DIR = CATALOG_DIR / "reports/quality-review/2026-10-26/corrected"
CACHE_DIR = CATALOG_DIR / "ingestion-cache"


def run_db_chunk_audit(db) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit active chunks in knowledge database."""
    print("Running database chunk quality checks...", flush=True)
    findings = []
    stats: dict[str, Any] = {}
    excluded = get_settings().quality_excluded_chunk_ids
    eligible = screened_evidence_sql(excluded)
    stats["excluded_known_quality_chunk_ids"] = [str(value) for value in excluded]

    # Total active chunks
    total_active_chunks = db.scalar(
        text(
            f"""
        SELECT count(*) FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN library_books b ON b.id = d.book_id
        JOIN collections col ON col.id = d.collection_id
        WHERE {eligible}
        """
        )
    )
    stats["total_active_chunks"] = total_active_chunks
    print(f"Total active chunks in DB: {total_active_chunks}", flush=True)

    # 1. Unicode replacement character '\ufffd'
    replacement_rows = db.execute(
        text(
            f"""
        SELECT c.id, c.document_id, d.book_id, d.book_generation, c.page_start, c.page_end, c.text,
               b.source_sha256, d.title, col.slug
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN library_books b ON b.id = d.book_id
        LEFT JOIN collections col ON col.id = d.collection_id
        WHERE {eligible}
          AND c.text LIKE '%\ufffd%'
        """
        )
    ).fetchall()

    stats["chunks_with_replacement_char"] = len(replacement_rows)
    print(f"Chunks with replacement char: {len(replacement_rows)}", flush=True)

    for row in replacement_rows:
        count = row.text.count("\ufffd")
        findings.append(
            {
                "resource_id": str(row.book_id) if row.book_id else str(row.document_id),
                "source_checksum": row.source_sha256 or "",
                "physical_page_range": f"{row.page_start}-{row.page_end}" if row.page_start else "",
                "prepared_generation": row.book_generation or 1,
                "document_id": str(row.document_id),
                "chunk_id": str(row.id),
                "category": "UNICODE_REPLACEMENT_CHAR",
                "severity": "HIGH",
                "evidence": f"Chunk contains {count} replacement char(s) (\\ufffd). Excerpt: {row.text[:80]!r}",
                "review_method": "AUTOMATED_SQL",
                "confidence": 1.0,
                "repair_action": "STAGE_SOURCE_ENCODING_REPAIR",
                "retest_result": "NEEDS_REVIEW",
            }
        )

    # 2. Control characters (excluding standard \t, \n, \r)
    control_rows = db.execute(
        text(
            rf"""
        SELECT c.id, c.document_id, d.book_id, d.book_generation, c.page_start, c.page_end, c.text,
               b.source_sha256
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN library_books b ON b.id = d.book_id
        JOIN collections col ON col.id = d.collection_id
        WHERE {eligible}
          AND c.text ~ '[\x01-\x08\x0b\x0c\x0e-\x1f]'
        LIMIT 100
        """
        )
    ).fetchall()

    stats["chunks_with_control_chars_sample"] = len(control_rows)
    for row in control_rows:
        findings.append(
            {
                "resource_id": str(row.book_id) if row.book_id else str(row.document_id),
                "source_checksum": row.source_sha256 or "",
                "physical_page_range": f"{row.page_start}-{row.page_end}" if row.page_start else "",
                "prepared_generation": row.book_generation or 1,
                "document_id": str(row.document_id),
                "chunk_id": str(row.id),
                "category": "UNESCAPED_CONTROL_CHAR",
                "severity": "LOW",
                "evidence": "Chunk contains unescaped non-printable ASCII control character(s)",
                "review_method": "AUTOMATED_SQL",
                "confidence": 1.0,
                "repair_action": "SANITIZE_CONTROL_CHARS",
                "retest_result": "NEEDS_REVIEW",
            }
        )

    # 3. Very short chunks (< 25 characters) that are not covers or numbers
    short_rows = db.execute(
        text(
            f"""
        SELECT c.id, c.document_id, d.book_id, d.book_generation, c.page_start, c.page_end, c.text,
               b.source_sha256
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN library_books b ON b.id = d.book_id
        JOIN collections col ON col.id = d.collection_id
        WHERE {eligible}
          AND length(trim(c.text)) < 25 AND length(trim(c.text)) > 0
        LIMIT 50
        """
        )
    ).fetchall()

    stats["sample_short_chunks"] = len(short_rows)
    for row in short_rows:
        stripped = row.text.strip()
        findings.append(
            {
                "resource_id": str(row.book_id) if row.book_id else str(row.document_id),
                "source_checksum": row.source_sha256 or "",
                "physical_page_range": f"{row.page_start}-{row.page_end}" if row.page_start else "",
                "prepared_generation": row.book_generation or 1,
                "document_id": str(row.document_id),
                "chunk_id": str(row.id),
                "category": "SHORT_CHUNK_BOUNDARY",
                "severity": "LOW",
                "evidence": f"Sparse chunk ({len(stripped)} chars): {stripped!r}",
                "review_method": "AUTOMATED_SQL",
                "confidence": 0.8,
                "repair_action": "EVALUATE_CHUNK_MERGE",
                "retest_result": "NEEDS_REVIEW",
            }
        )

    return findings, stats


def audit_ocr_pages(
    catalog: dict[str, Any], status: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Heuristically screen current OCR pages, retaining explicit blank outcomes."""
    print("Auditing current OCR pages...", flush=True)
    findings = []
    stats: dict[str, Any] = {
        "total_ocr_resources": 0,
        "total_ocr_pages": 0,
        "ocr_pages_with_math_patterns": 0,
        "ocr_pages_with_table_patterns": 0,
        "ocr_pages_with_high_noise": 0,
        "ocr_pages_with_broken_operators": 0,
        "ocr_pages_without_heuristic_flags": 0,
    }

    status_resources = status.get("resources", {})
    catalog_resources = {
        r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])
    }

    for res_id, res_info in status_resources.items():
        prep_path_str = res_info.get("preparation_path")
        if not prep_path_str:
            continue
        prep_path = Path(prep_path_str)
        if not prep_path.exists():
            continue

        prep = json.loads(prep_path.read_text(encoding="utf-8"))
        ocr_pages_list = prep.get("ocr_pages", [])
        if not ocr_pages_list:
            continue

        stats["total_ocr_resources"] += 1
        cat_row = catalog_resources.get(res_id, {})
        source_sha = cat_row.get("sha256", prep.get("source_sha256", ""))
        generation = res_info.get("indexed_revision")

        # Build map of part pages for OCR pages
        ocr_set = set(ocr_pages_list)
        audited_pages_for_res = set()
        for part in prep.get("parts", []):
            start = part.get("first_page", part.get("page_start", 0))
            end = part.get("last_page", part.get("page_end", 0))
            if not any(start <= p <= end for p in ocr_set):
                continue
            part_path = Path(part["path"])
            if not part_path.exists():
                continue
            part_data = json.loads(part_path.read_text(encoding="utf-8"))
            for p in part_data.get("pages", []):
                p_num = p["page"]
                if p_num not in ocr_set:
                    continue

                stats["total_ocr_pages"] += 1
                audited_pages_for_res.add(p_num)
                text_content = p.get("text", "")
                stripped = text_content.strip()
                chars_len = len(stripped)

                # Heuristic checks on OCR text:
                # 1. High noise / low alpha ratio
                alpha_count = sum(1 for c in stripped if c.isalpha())
                alpha_ratio = alpha_count / chars_len if chars_len else 0
                symbol_count = sum(1 for c in stripped if not c.isalnum() and not c.isspace())
                symbol_ratio = symbol_count / chars_len if chars_len else 0

                has_math = bool(
                    re.search(r"(\b\d+\s*[+\-*/=^<>≤≥]\s*\d+\b|[α-ωΑ-Ω]|∑|∫|√|±|∂)", text_content)
                )
                has_table = bool(
                    re.search(r"(\|[ -]+\||(\b\w+\b\s{3,}\b\w+\b.*?\n){3,})", text_content)
                )
                broken_ops = bool(
                    re.search(
                        r"(\+\s*\+|-\s*-|/\s*/|\*\s*\*|=\s*=|_\s*_|\b[a-z]\s+=\s+\n)", text_content
                    )
                )

                if has_math:
                    stats["ocr_pages_with_math_patterns"] += 1
                if has_table:
                    stats["ocr_pages_with_table_patterns"] += 1
                if broken_ops:
                    stats["ocr_pages_with_broken_operators"] += 1

                # If noisy OCR
                if chars_len > 60 and alpha_ratio < 0.35 and symbol_ratio > 0.30:
                    stats["ocr_pages_with_high_noise"] += 1
                    findings.append(
                        {
                            "resource_id": res_id,
                            "source_checksum": source_sha,
                            "physical_page_range": str(p_num),
                            "prepared_generation": generation,
                            "document_id": "",
                            "chunk_id": "",
                            "category": "OCR_HIGH_NOISE",
                            "severity": "MEDIUM",
                            "evidence": f"OCR noise on page {p_num}: alpha_ratio={alpha_ratio:.2f}, symbol_ratio={symbol_ratio:.2f}, total_chars={chars_len}",
                            "review_method": "AUTOMATED_OCR_ANALYSIS",
                            "confidence": 0.88,
                            "repair_action": "RETAIN_WITH_OCR_WARNING_NOTICE",
                            "retest_result": "NEEDS_REVIEW",
                        }
                    )
                elif broken_ops and has_math:
                    findings.append(
                        {
                            "resource_id": res_id,
                            "source_checksum": source_sha,
                            "physical_page_range": str(p_num),
                            "prepared_generation": generation,
                            "document_id": "",
                            "chunk_id": "",
                            "category": "OCR_FORMULA_INTEGRITY_RISK",
                            "severity": "MEDIUM",
                            "evidence": f"OCR formula notation risk on page {p_num}: broken operator patterns detected in mathematical passage",
                            "review_method": "AUTOMATED_OCR_ANALYSIS",
                            "confidence": 0.82,
                            "repair_action": "FLAG_MATHEMATICAL_OCR_LIMITATION",
                            "retest_result": "NEEDS_REVIEW",
                        }
                    )
                else:
                    stats["ocr_pages_without_heuristic_flags"] += 1

        # Check any OCR pages not present in text parts (e.g. blank pages)
        missing_from_parts = ocr_set - audited_pages_for_res
        blank_set = set(prep.get("blank_pages") or [])
        for p_num in sorted(missing_from_parts):
            stats["total_ocr_pages"] += 1
            if p_num in blank_set:
                stats["ocr_pages_blank"] = stats.get("ocr_pages_blank", 0) + 1
                findings.append(
                    {
                        "resource_id": res_id,
                        "source_checksum": source_sha,
                        "physical_page_range": str(p_num),
                        "prepared_generation": generation,
                        "document_id": "",
                        "chunk_id": "",
                        "category": "OCR_BLANK_PAGE",
                        "severity": "LOW",
                        "evidence": f"OCR page {p_num} produced zero text; verified blank/non-text page in preparation",
                        "review_method": "AUTOMATED_OCR_ANALYSIS",
                        "confidence": 1.0,
                        "repair_action": "RETAIN_BLANK_PAGE_RECORD",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )
            else:
                stats["ocr_pages_missing_text"] = stats.get("ocr_pages_missing_text", 0) + 1
                findings.append(
                    {
                        "resource_id": res_id,
                        "source_checksum": source_sha,
                        "physical_page_range": str(p_num),
                        "prepared_generation": generation,
                        "document_id": "",
                        "chunk_id": "",
                        "category": "OCR_PAGE_MISSING_TEXT",
                        "severity": "MEDIUM",
                        "evidence": f"OCR page {p_num} not found in parts and not marked blank",
                        "review_method": "AUTOMATED_OCR_ANALYSIS",
                        "confidence": 0.95,
                        "repair_action": "VERIFY_PAGE_EXTRACTION",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )

    print(
        f"Audited {stats['total_ocr_pages']} OCR pages across {stats['total_ocr_resources']} resources.",
        flush=True,
    )
    return findings, stats


def audit_visual_review_groups() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit the 12 exact-pixel visual review groups for classification consistency."""
    print("Auditing visual review groups...", flush=True)
    findings = []
    stats: dict[str, Any] = {}

    vr_path = CATALOG_DIR / "reports/visual-review.json"
    if not vr_path.exists():
        return findings, {"error": "visual-review.json missing"}

    vr_data = json.loads(vr_path.read_text(encoding="utf-8"))
    groups = vr_data.get("groups", {})
    stats["total_groups"] = len(groups)

    classifications = Counter()
    total_instances = 0

    for digest_key, group in groups.items():
        cls = group.get("classification")
        classifications[cls] += 1
        text_val = group.get("text", "")
        instances = group.get("instances", [])
        total_instances += len(instances)

        # Check: Visual description must NOT be classified as transcriptions
        if (
            cls == "VISUAL_DESCRIPTION"
            and text_val
            and "Visual description" not in text_val
            and "transcription" in text_val.lower()
        ):
            findings.append(
                {
                    "resource_id": instances[0]["id"] if instances else "",
                    "source_checksum": instances[0].get("source_sha256", "") if instances else "",
                    "physical_page_range": str(instances[0].get("page", "")) if instances else "",
                    "prepared_generation": 3,
                    "document_id": "",
                    "chunk_id": "",
                    "category": "VISUAL_CLASSIFICATION_MISMATCH",
                    "severity": "HIGH",
                    "evidence": f"Group {digest_key[:12]} marked VISUAL_DESCRIPTION but text describes transcription",
                    "review_method": "AUTOMATED_SEMANTIC_CHECK",
                    "confidence": 0.95,
                    "repair_action": "RECLASSIFY_EXACT_CATEGORY",
                    "retest_result": "NEEDS_REVIEW",
                }
            )

        # Check: Header transcriptions must state header transcription
        if cls == "VISUALLY_REVIEWED_TRANSCRIPTION":
            if not text_val or len(text_val.strip()) == 0:
                findings.append(
                    {
                        "resource_id": instances[0]["id"] if instances else "",
                        "source_checksum": instances[0].get("source_sha256", "")
                        if instances
                        else "",
                        "physical_page_range": str(instances[0].get("page", ""))
                        if instances
                        else "",
                        "prepared_generation": 3,
                        "document_id": "",
                        "chunk_id": "",
                        "category": "VISUAL_TRANSCRIPTION_EMPTY",
                        "severity": "HIGH",
                        "evidence": f"Group {digest_key[:12]} marked VISUALLY_REVIEWED_TRANSCRIPTION has empty text",
                        "review_method": "AUTOMATED_SEMANTIC_CHECK",
                        "confidence": 1.0,
                        "repair_action": "SUPPLY_VERIFIED_TRANSCRIPTION",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )

    stats["classifications"] = dict(classifications)
    stats["total_instances"] = total_instances
    print(
        f"Visual review: {len(groups)} groups, {total_instances} instances. Breakdown: {dict(classifications)}",
        flush=True,
    )
    return findings, stats


def audit_compilation_attribution(
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit the 159 compilation ranges for correct attribution."""
    print("Auditing compilation attribution across 159 ranges...", flush=True)
    findings = []
    stats: dict[str, Any] = {
        "total_ranges": 0,
        "named_references": 0,
        "generic_windows": 0,
        "attribution_defects": 0,
    }

    comp_plan_path = CATALOG_DIR / "compilation-coverage-plan.json"
    if not comp_plan_path.exists():
        return findings, {"error": "compilation-coverage-plan.json missing"}

    plan = json.loads(comp_plan_path.read_text(encoding="utf-8"))
    ranges = plan.get("existing_roadmap_ranges", []) + plan.get("remaining_windows", [])
    stats["total_ranges"] = len(ranges)
    cat_by_id = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}

    for item in ranges:
        res_id = item.get("id")
        page_range = item.get("page_range", [0, 0])
        first_page, last_page = page_range[0], page_range[-1]
        title = cat_by_id.get(res_id, {}).get("title", "")

        # Political science: 10421-11059
        if first_page == 10421 and last_page == 11059:
            stats["named_references"] += 1
            if "Political Science" not in title:
                findings.append(
                    {
                        "resource_id": res_id,
                        "source_checksum": "",
                        "physical_page_range": "10421-11059",
                        "prepared_generation": 3,
                        "document_id": "",
                        "chunk_id": "",
                        "category": "COMPILATION_NAMED_TITLE_MISMATCH",
                        "severity": "HIGH",
                        "evidence": f"Verified Political Science range has unexpected title: {title!r}",
                        "review_method": "AUTOMATED_METADATA_CHECK",
                        "confidence": 1.0,
                        "repair_action": "CORRECT_NAMED_TITLE",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )
        # Psychology: 35189-35971
        elif first_page == 35189 and last_page == 35971:
            stats["named_references"] += 1
            if "Psychology" not in title:
                findings.append(
                    {
                        "resource_id": res_id,
                        "source_checksum": "",
                        "physical_page_range": "35189-35971",
                        "prepared_generation": 3,
                        "document_id": "",
                        "chunk_id": "",
                        "category": "COMPILATION_NAMED_TITLE_MISMATCH",
                        "severity": "HIGH",
                        "evidence": f"Verified Psychology range has unexpected title: {title!r}",
                        "review_method": "AUTOMATED_METADATA_CHECK",
                        "confidence": 1.0,
                        "repair_action": "CORRECT_NAMED_TITLE",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )
        else:
            stats["generic_windows"] += 1
            # Must be labeled 'Mixed local compilation' and must NOT attribute specific OpenStax books
            if not title.startswith("Mixed local compilation"):
                stats["attribution_defects"] += 1
                findings.append(
                    {
                        "resource_id": res_id,
                        "source_checksum": "",
                        "physical_page_range": f"{first_page}-{last_page}",
                        "prepared_generation": 3,
                        "document_id": "",
                        "chunk_id": "",
                        "category": "COMPILATION_OVERATTRIBUTION_DEFECT",
                        "severity": "HIGH",
                        "evidence": f"Unverified window {first_page}-{last_page} should start with 'Mixed local compilation', got {title!r}",
                        "review_method": "AUTOMATED_METADATA_CHECK",
                        "confidence": 1.0,
                        "repair_action": "STANDARDIZE_UNVERIFIED_COMPILATION_TITLE",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )

    print(
        f"Compilation audit: {stats['total_ranges']} ranges ({stats['named_references']} named, {stats['generic_windows']} generic, {stats['attribution_defects']} defects).",
        flush=True,
    )
    return findings, stats


def audit_summaries_and_completeness(
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit whether summaries, study guides, or partial resources are clearly flagged in metadata."""
    print("Auditing book completeness and summaries...", flush=True)
    findings = []
    stats: dict[str, Any] = {
        "total_resources_checked": 0,
        "verified_summaries": 0,
        "verified_study_guides": 0,
        "unflagged_summaries": 0,
    }

    resources = catalog["resources"] + catalog.get("virtual_books", [])
    for row in resources:
        stats["total_resources_checked"] += 1
        coverage_note = row.get("metadata", {}).get("coverage_note", "") or ""
        tags = [t.lower() for t in row.get("tags", [])]

        is_summary = classify_representation(row) == "PUBLISHER_SUMMARY"
        is_study_guide = classify_representation(row) == "COURSE_STUDY_GUIDE"
        has_summary_note = bool(coverage_note) or any("summary" in t for t in tags)

        if is_summary:
            if has_summary_note:
                stats["verified_summaries"] += 1
                findings.append(
                    {
                        "resource_id": row["id"],
                        "source_checksum": row.get("sha256", ""),
                        "physical_page_range": f"1-{row.get('pdf_pages', 1)}",
                        "prepared_generation": row.get("active_generation", 1),
                        "document_id": "",
                        "chunk_id": "",
                        "category": "SUMMARY_NOTICE_PRESENT",
                        "severity": "INFO",
                        "evidence": f"Commercial summary title {row.get('title')!r} verified with explicit coverage note: {coverage_note[:80]!r}",
                        "review_method": "AUTOMATED_METADATA_SCAN",
                        "confidence": 1.0,
                        "repair_action": "NONE_CATALOG_NOTICE_PRESENT",
                        "retest_result": "CATALOG_NOTE_PRESENT_RUNTIME_NOT_CHECKED",
                    }
                )
            else:
                stats["unflagged_summaries"] += 1
                findings.append(
                    {
                        "resource_id": row["id"],
                        "source_checksum": row.get("sha256", ""),
                        "physical_page_range": f"1-{row.get('pdf_pages', 1)}",
                        "prepared_generation": row.get("active_generation", 1),
                        "document_id": "",
                        "chunk_id": "",
                        "category": "SUMMARY_METADATA_OMISSION",
                        "severity": "MEDIUM",
                        "evidence": f"Resource title {row.get('title')!r} indicates summary, but coverage_note does not explicitly declare it",
                        "review_method": "AUTOMATED_METADATA_SCAN",
                        "confidence": 0.95,
                        "repair_action": "ATTACH_SUMMARY_COVERAGE_NOTE",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )
        elif is_study_guide:
            if has_summary_note:
                stats["verified_study_guides"] += 1
                findings.append(
                    {
                        "resource_id": row["id"],
                        "source_checksum": row.get("sha256", ""),
                        "physical_page_range": f"1-{row.get('pdf_pages', 1)}",
                        "prepared_generation": row.get("active_generation", 1),
                        "document_id": "",
                        "chunk_id": "",
                        "category": "STUDY_GUIDE_NOTICE_PRESENT",
                        "severity": "INFO",
                        "evidence": f"Academic study guide title {row.get('title')!r} verified with explicit coverage note: {coverage_note[:80]!r}",
                        "review_method": "AUTOMATED_METADATA_SCAN",
                        "confidence": 1.0,
                        "repair_action": "NONE_CATALOG_NOTICE_PRESENT",
                        "retest_result": "CATALOG_NOTE_PRESENT_RUNTIME_NOT_CHECKED",
                    }
                )
            else:
                stats["unflagged_summaries"] += 1
                findings.append(
                    {
                        "resource_id": row["id"],
                        "source_checksum": row.get("sha256", ""),
                        "physical_page_range": f"1-{row.get('pdf_pages', 1)}",
                        "prepared_generation": row.get("active_generation", 1),
                        "document_id": "",
                        "chunk_id": "",
                        "category": "STUDY_GUIDE_METADATA_OMISSION",
                        "severity": "MEDIUM",
                        "evidence": f"Resource title {row.get('title')!r} indicates study guide, but coverage_note does not explicitly declare it",
                        "review_method": "AUTOMATED_METADATA_SCAN",
                        "confidence": 0.95,
                        "repair_action": "ATTACH_COVERAGE_NOTE",
                        "retest_result": "NEEDS_REVIEW",
                    }
                )

    print(
        f"Completeness audit: checked {stats['total_resources_checked']} resources, verified {stats['verified_summaries'] + stats['verified_study_guides']} summaries/guides, {stats['unflagged_summaries']} unflagged.",
        flush=True,
    )
    return findings, stats


def export_findings(findings: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "quality-findings.jsonl"
    csv_path = output_dir / "quality-findings.csv"

    # Write JSONL
    with jsonl_path.open("w", encoding="utf-8") as f:
        for finding in findings:
            f.write(json.dumps(finding, ensure_ascii=False) + "\n")

    # Write CSV
    headers = [
        "resource_id",
        "source_checksum",
        "physical_page_range",
        "prepared_generation",
        "document_id",
        "chunk_id",
        "category",
        "severity",
        "evidence",
        "review_method",
        "confidence",
        "repair_action",
        "retest_result",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for finding in findings:
            writer.writerow(finding)

    print(f"Exported {len(findings)} findings to {jsonl_path} and {csv_path}", flush=True)
    return jsonl_path, csv_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    catalog = read_catalog(CATALOG_DIR / "library.json")
    status = json.loads((CATALOG_DIR / "ingestion-status.json").read_text(encoding="utf-8"))

    all_findings = []
    coverage_record: dict[str, Any] = {
        "audit_timestamp": datetime.now(UTC).isoformat(),
        "method": "Automated screening of current eligible evidence; no new visual/semantic certification",
        "new_manual_visual_pages_reviewed": 0,
        "catalog_summary": status.get("summary", {}),
    }

    with session() as db:
        db_findings, db_stats = run_db_chunk_audit(db)
        all_findings.extend(db_findings)
        coverage_record["db_chunk_audit"] = db_stats

    ocr_findings, ocr_stats = audit_ocr_pages(catalog, status)
    all_findings.extend(ocr_findings)
    coverage_record["ocr_audit"] = ocr_stats
    coverage_record["ocr_pages_screened_total"] = ocr_stats["total_ocr_pages"]

    vr_findings, vr_stats = audit_visual_review_groups()
    all_findings.extend(vr_findings)
    coverage_record["visual_review_audit"] = vr_stats

    comp_findings, comp_stats = audit_compilation_attribution(catalog)
    all_findings.extend(comp_findings)
    coverage_record["compilation_attribution_audit"] = comp_stats

    summary_findings, summary_stats = audit_summaries_and_completeness(catalog)
    all_findings.extend(summary_findings)
    coverage_record["completeness_audit"] = summary_stats

    # Export findings
    jsonl_p, csv_p = export_findings(all_findings, OUTPUT_DIR)

    # Export review coverage
    coverage_record["total_findings_count"] = len(all_findings)
    coverage_record["findings_by_severity"] = dict(Counter(f["severity"] for f in all_findings))
    coverage_record["findings_by_category"] = dict(Counter(f["category"] for f in all_findings))
    coverage_record["elapsed_seconds"] = round(time.time() - start_time, 2)

    cov_path = OUTPUT_DIR / "REVIEW_COVERAGE.json"
    cov_path.write_text(json.dumps(coverage_record, indent=2), encoding="utf-8")
    print(f"Exported coverage record to {cov_path}", flush=True)


if __name__ == "__main__":
    main()
