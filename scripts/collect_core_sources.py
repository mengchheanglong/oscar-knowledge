"""Collect public CORE Econ TOC-linked HTML, preserving original bytes and notices.

No login, gated solution access, source PDF overwrite, or redistribution is performed.
Downloads go to existing Social Systems subject folders; provenance stays in Catalog.
"""

import argparse
import concurrent.futures
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

SEEDS = {
    "doing-economics": (
        "https://books.core-econ.org/doing-economics/book/text/0-3-contents.html",
        "Research, Data & Thinking Tools",
    ),
    "economy-micro": (
        "https://books.core-econ.org/the-economy/microeconomics/0-3-contents.html",
        "Economics & Development",
    ),
    "economy-macro": (
        "https://books.core-econ.org/the-economy/macroeconomics/0-3-contents.html",
        "Economics & Development",
    ),
}


def collect(root: Path):
    records = []
    for book, (toc, category) in SEEDS.items():
        folder = root / "Social Systems" / category
        if not folder.is_dir():
            raise ValueError("EXISTING_SUBJECT_FOLDER_REQUIRED")
        prefix = toc.rsplit("/", 1)[0] + "/"
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            response = client.get(toc)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            urls = {toc, urljoin(prefix, "0-2-copyright.html")}
            for a in soup.select("a[href]"):
                url = urldefrag(urljoin(toc, a["href"]))[0]
                if url.startswith(prefix) and url.endswith(".html") and not urlsplit(url).query:
                    # Instructor solutions can require separate permission. Keep
                    # them out even when a TOC happens to advertise a public link.
                    if "solution" not in url.lower():
                        urls.add(url)
            if len(urls) > 300:
                raise ValueError("SOURCE_PAGE_BUDGET")
            basenames = Counter(urlsplit(url).path.rsplit("/", 1)[-1].casefold() for url in urls)

            def download(url):
                filename = f"CORE-{book}-{urlsplit(url).path.rsplit('/', 1)[-1]}"
                if basenames[urlsplit(url).path.rsplit("/", 1)[-1].casefold()] > 1:
                    filename = (
                        filename.removesuffix(".html")
                        + "-"
                        + hashlib.sha256(url.encode()).hexdigest()[:8]
                        + ".html"
                    )
                target = folder / filename
                if target.exists():
                    data = target.read_bytes()
                else:
                    with client.stream("GET", url) as fetched:
                        fetched.raise_for_status()
                        if urlsplit(str(fetched.url)).hostname != "books.core-econ.org":
                            raise ValueError("UNEXPECTED_REDIRECT")
                        data = b""
                        for chunk in fetched.iter_bytes():
                            data += chunk
                            if len(data) > 2_000_000:
                                raise ValueError("PAGE_BYTE_LIMIT")
                    target.write_bytes(data)
                page = BeautifulSoup(data, "html.parser")
                title = page.title.get_text(" ", strip=True) if page.title else filename
                return {
                    "book": book,
                    "url": url,
                    "path": str(target),
                    "title": title,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                    "scope": "Private noncommercial study; preserve publisher notices and third-party exceptions",
                    "license": "See retained CORE copyright page; no permission to distribute modified material implied",
                }

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(download, url): url for url in sorted(urls)}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        records.append(future.result())
                    except Exception:
                        records.append(
                            {"book": book, "url": futures[future], "status": "UNAVAILABLE"}
                        )
        print(
            book,
            "collected",
            sum(r.get("book") == book and "sha256" in r for r in records),
            flush=True,
        )
    output = root / "Catalog" / "core-acquisition.json"
    output.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("D:/AI/OSCAR/Knowledge"))
    args = parser.parse_args()
    result = collect(args.root)
    print("Public HTML pages saved:", sum("sha256" in r for r in result))
