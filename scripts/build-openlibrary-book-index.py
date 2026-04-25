#!/usr/bin/env python3
"""Build a compact Kids Bucket List book catalog from OpenLibrary dumps.

Inputs are the monthly OpenLibrary TSV dumps from:
https://openlibrary.org/developers/dumps

Recommended sources:
- ol_dump_authors_latest.txt.gz
- ol_dump_editions_latest.txt.gz

The script streams dump files, keeps the published JSON small enough for
GitHub Pages, and writes the schema consumed by the iOS app.
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_LANGUAGES = {"deu", "ger", "de", "eng", "en"}
DEFAULT_SUBJECT_HINTS = (
    "juvenile",
    "children",
    "kids",
    "picture book",
    "bilderbuch",
    "kinder",
    "young adult",
    "read-aloud",
)


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("rt", encoding="utf-8", errors="replace")


def iter_dump_json(path: Path):
    with open_text(path) as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) != 5:
                continue
            try:
                yield json.loads(parts[4])
            except json.JSONDecodeError:
                continue


def clean(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def clean_list(values: Any, limit: int | None = None) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = [item for item in (clean(value) for value in values) if item]
    return cleaned[:limit] if limit else cleaned


def key_tail(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return key.rsplit("/", 1)[-1]


def load_authors(path: Optional[Path]) -> dict[str, str]:
    if path is None:
        return {}

    authors: dict[str, str] = {}
    for record in iter_dump_json(path):
        key = clean(record.get("key"))
        name = clean(record.get("name"))
        if key and name:
            authors[key] = name
    return authors


def language_codes(record: dict[str, Any]) -> list[str]:
    values = []
    for language in record.get("languages") or []:
        key = language.get("key") if isinstance(language, dict) else None
        tail = key_tail(clean(key))
        if tail:
            values.append(tail.lower())
    return values


def author_names(record: dict[str, Any], authors: dict[str, str]) -> list[str]:
    values = []
    for author in record.get("authors") or []:
        key = author.get("key") if isinstance(author, dict) else None
        name = authors.get(key or "")
        if name:
            values.append(name)
    return values[:4]


def subjects(record: dict[str, Any]) -> list[str]:
    return clean_list(record.get("subjects"), limit=8)


def looks_family_relevant(record: dict[str, Any], allowed_languages: set[str]) -> bool:
    title = clean(record.get("title"))
    if title is None:
        return False

    codes = language_codes(record)
    if codes and not any(code in allowed_languages for code in codes):
        return False

    subject_text = " ".join(subjects(record)).lower()
    if subject_text:
        return any(hint in subject_text for hint in DEFAULT_SUBJECT_HINTS)

    # Keep records without subjects if they have strong ISBN metadata. This lets
    # ISBN search still work for editions whose subjects are only on the work.
    return bool(clean_list(record.get("isbn_10")) or clean_list(record.get("isbn_13")))


def make_record(record: dict[str, Any], authors: dict[str, str]) -> dict[str, Any]:
    work_key = None
    works = record.get("works")
    if isinstance(works, list) and works:
        first_work = works[0]
        if isinstance(first_work, dict):
            work_key = clean(first_work.get("key"))

    edition_key = clean(record.get("key"))
    record_id = key_tail(work_key) or key_tail(edition_key) or clean(record.get("title")) or "unknown"
    cover_values = record.get("covers")
    cover_id = cover_values[0] if isinstance(cover_values, list) and cover_values else None

    output: dict[str, Any] = {
        "id": record_id,
        "openLibraryKey": work_key or edition_key,
        "title": clean(record.get("title")) or "Untitled Book",
        "authors": author_names(record, authors),
        "publishedDate": clean(record.get("publish_date")),
        "languages": language_codes(record),
        "subjects": subjects(record),
        "pageCount": record.get("number_of_pages"),
        "publisher": next(iter(clean_list(record.get("publishers"), limit=1)), None),
        "isbn10": clean_list(record.get("isbn_10")),
        "isbn13": clean_list(record.get("isbn_13")),
        "coverID": cover_id if isinstance(cover_id, int) else None,
        "openLibraryURL": f"https://openlibrary.org{work_key or edition_key}" if (work_key or edition_key) else None,
    }
    return {key: value for key, value in output.items() if value not in (None, [], "")}


def build_index(args: argparse.Namespace) -> None:
    authors = load_authors(args.authors_dump)
    allowed_languages = set(args.languages)
    seen_ids: set[str] = set()
    records: list[dict[str, Any]] = []

    for record in iter_dump_json(args.editions_dump):
        if not looks_family_relevant(record, allowed_languages):
            continue

        compact = make_record(record, authors)
        record_id = compact["id"]
        if record_id in seen_ids:
            continue

        seen_ids.add(record_id)
        records.append(compact)

        if len(records) >= args.limit:
            break

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "OpenLibrary monthly dump",
        "records": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} records to {args.output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--editions-dump", type=Path, required=True)
    parser.add_argument("--authors-dump", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/books/search-index.json"))
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--languages", nargs="+", default=sorted(DEFAULT_LANGUAGES))
    return parser.parse_args()


if __name__ == "__main__":
    build_index(parse_args())
