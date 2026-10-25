import hashlib
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.ingestion.loaders import SourceError
from app.ingestion.pipeline import enqueue
from app.security import public_source_url


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection: str = "mba-business"
    institution: str
    course_code: str
    course_title: str
    subject: str
    course_page: str
    download_url: str | None = None
    local_file: str | None = None
    title: str | None = None
    license: str
    license_url: str | None = None
    approved: bool = False
    notes: str = ""
    ingestion_status: str = "DISCOVERED"
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class Manifest(BaseModel):
    version: int = 1
    entries: list[Entry] = Field(max_length=100)


def download(url: str, target: Path, settings: Settings, expected_sha256: str | None = None):
    import ipaddress

    parsed = urlsplit(url)
    if public_source_url(url) != url or parsed.hostname not in {"ocw.mit.edu"}:
        raise SourceError("DOWNLOAD_HOST_NOT_ALLOWED")
    if expected_sha256 and target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected_sha256:
            raise SourceError("DOWNLOAD_CHECKSUM_MISMATCH")
        return
    if not all(
        ipaddress.ip_address(item[4][0]).is_global
        for item in socket.getaddrinfo(parsed.hostname, 443)
    ):
        raise SourceError("DOWNLOAD_ADDRESS_NOT_PUBLIC")
    # No redirects, proxies, cookies, archive extraction, or credentials. Only a curator's exact URL.
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise SourceError("DOWNLOAD_HTTP_ERROR")
                size = 0
                with temporary.open("wb") as stream:
                    for part in response.iter_bytes(65536):
                        size += len(part)
                        if size > settings.max_file_bytes:
                            raise SourceError("DOWNLOAD_TOO_LARGE")
                        stream.write(part)
        if (
            expected_sha256
            and hashlib.sha256(temporary.read_bytes()).hexdigest() != expected_sha256
        ):
            raise SourceError("DOWNLOAD_CHECKSUM_MISMATCH")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def import_manifest(db, path: Path, settings: Settings, download_approved=False):
    if path.stat().st_size > 1_000_000:
        raise SourceError("MANIFEST_TOO_LARGE")
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    jobs = []
    for entry in manifest.entries:
        if not entry.approved:
            continue
        if entry.local_file:
            root = path.resolve().parent
            source = (root / entry.local_file).resolve()
            if not source.is_relative_to(root):
                raise SourceError("MANIFEST_PATH_ESCAPE")
        elif entry.download_url and download_approved:
            suffix = Path(urlsplit(entry.download_url).path).suffix.lower()
            if suffix not in {
                ".pdf",
                ".txt",
                ".html",
                ".md",
                ".srt",
                ".vtt",
                ".docx",
                ".xlsx",
                ".csv",
            }:
                raise SourceError("DOWNLOAD_FORMAT_NOT_ALLOWED")
            source = Path("data/raw") / (
                hashlib.sha256(entry.download_url.encode()).hexdigest() + suffix
            )
            download(entry.download_url, source, settings, entry.sha256)
        else:
            continue
        if entry.sha256 and hashlib.sha256(source.read_bytes()).hexdigest() != entry.sha256:
            raise SourceError("SOURCE_CHECKSUM_MISMATCH")
        jobs.append(
            enqueue(
                db,
                source,
                entry.collection,
                approved=True,
                canonical_key=entry.download_url or entry.course_page + "#" + str(entry.local_file),
                source_url=public_source_url(entry.download_url or entry.course_page),
                title=entry.title or entry.course_title,
                institution=entry.institution,
                course_code=entry.course_code,
                course_title=entry.course_title,
                subject=entry.subject,
                license_type=entry.license,
                license_url=entry.license_url,
                usage_notes=entry.notes,
            )
        )
    return jobs
