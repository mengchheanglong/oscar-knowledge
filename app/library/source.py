"""Process-local hash verification reuse; changed file identity always invalidates it."""

from pathlib import Path

from app.library.catalog import digest

_verified: dict[str, tuple[tuple[int, ...], str]] = {}


def fingerprint(path: Path) -> tuple[int, ...]:
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def verify_source(resource, *, force=False):
    path = Path(resource["absolute_path"])
    if path.is_symlink():
        raise ValueError("BOOK_FILE_LIMIT")
    before = fingerprint(path)
    key = str(path.resolve())
    expected = resource["sha256"]
    if force or _verified.get(key) != (before, expected):
        if digest(path) != expected or fingerprint(path) != before:
            raise ValueError("SOURCE_CHECKSUM_CHANGED")
        _verified[key] = before, expected
    return before
