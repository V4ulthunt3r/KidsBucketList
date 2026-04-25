#!/usr/bin/env python3
"""Build the Kids Bucket List SQLite book catalog from OpenLibrary dumps.

Inputs are the monthly OpenLibrary TSV dumps from:
https://openlibrary.org/developers/dumps

Recommended sources:
- ol_dump_authors_latest.txt.gz
- ol_dump_editions_latest.txt.gz

The script streams dump files, writes a SQLite database with FTS5 search, and
creates a manifest consumed by the iOS app.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
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

    return {
        "id": record_id,
        "open_library_key": work_key or edition_key,
        "title": clean(record.get("title")) or "Untitled Book",
        "subtitle": clean(record.get("subtitle")),
        "authors": ", ".join(author_names(record, authors)),
        "published_date": clean(record.get("publish_date")),
        "language_code": next(iter(language_codes(record)), None),
        "subjects": ", ".join(subjects(record)),
        "page_count": record.get("number_of_pages"),
        "publisher": next(iter(clean_list(record.get("publishers"), limit=1)), None),
        "isbn10": ", ".join(clean_list(record.get("isbn_10"))),
        "isbn13": ", ".join(clean_list(record.get("isbn_13"))),
        "cover_id": cover_id if isinstance(cover_id, int) else None,
        "open_library_url": f"https://openlibrary.org{work_key or edition_key}" if (work_key or edition_key) else None,
        "description": clean(record.get("description")) if isinstance(record.get("description"), str) else None,
    }


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS books_fts;
        DROP TABLE IF EXISTS books;

        CREATE TABLE books (
          id TEXT PRIMARY KEY,
          open_library_key TEXT,
          title TEXT NOT NULL,
          subtitle TEXT,
          authors TEXT,
          published_date TEXT,
          language_code TEXT,
          subjects TEXT,
          page_count INTEGER,
          publisher TEXT,
          isbn10 TEXT,
          isbn13 TEXT,
          cover_id INTEGER,
          open_library_url TEXT,
          description TEXT
        );

        CREATE INDEX books_isbn10_idx ON books(isbn10);
        CREATE INDEX books_isbn13_idx ON books(isbn13);
        CREATE INDEX books_title_idx ON books(title);

        CREATE VIRTUAL TABLE books_fts USING fts5(
          title,
          subtitle,
          authors,
          subjects,
          isbn10,
          isbn13,
          content='books',
          content_rowid='rowid'
        );

        CREATE TRIGGER books_ai AFTER INSERT ON books BEGIN
          INSERT INTO books_fts(rowid, title, subtitle, authors, subjects, isbn10, isbn13)
          VALUES (new.rowid, new.title, new.subtitle, new.authors, new.subjects, new.isbn10, new.isbn13);
        END;
        """
    )


def insert_record(connection: sqlite3.Connection, record: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO books (
          id, open_library_key, title, subtitle, authors, published_date,
          language_code, subjects, page_count, publisher, isbn10, isbn13,
          cover_id, open_library_url, description
        )
        VALUES (
          :id, :open_library_key, :title, :subtitle, :authors, :published_date,
          :language_code, :subjects, :page_count, :publisher, :isbn10, :isbn13,
          :cover_id, :open_library_url, :description
        );
        """,
        record,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_index(args: argparse.Namespace) -> None:
    authors = load_authors(args.authors_dump)
    allowed_languages = set(args.languages)
    seen_ids: set[str] = set()
    record_count = 0

    args.database_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    if args.database_output.exists():
        args.database_output.unlink()

    connection = sqlite3.connect(args.database_output)
    try:
        create_schema(connection)
        with connection:
            for dump_record in iter_dump_json(args.editions_dump):
                if not looks_family_relevant(dump_record, allowed_languages):
                    continue

                record = make_record(dump_record, authors)
                record_id = record["id"]
                if record_id in seen_ids:
                    continue

                seen_ids.add(record_id)
                insert_record(connection, record)
                record_count += 1

                if record_count >= args.limit:
                    break

        connection.execute("INSERT INTO books_fts(books_fts) VALUES ('optimize');")
        connection.commit()
        connection.execute("VACUUM;")
    finally:
        connection.close()

    manifest = {
        "version": args.version,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "OpenLibrary monthly dump",
        "databaseURL": args.database_url,
        "sha256": sha256_file(args.database_output),
        "recordCount": record_count,
    }
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {record_count} records to {args.database_output}")
    print(f"Wrote manifest to {args.manifest_output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--editions-dump", type=Path, required=True)
    parser.add_argument("--authors-dump", type=Path)
    parser.add_argument("--database-output", type=Path, default=Path("data/books/books.sqlite"))
    parser.add_argument("--manifest-output", type=Path, default=Path("data/books/manifest.json"))
    parser.add_argument("--database-url", default="https://v4ulthunt3r.github.io/KidsBucketList/data/books/books.sqlite")
    parser.add_argument("--version", default=datetime.now(timezone.utc).strftime("%Y-%m"))
    parser.add_argument("--limit", type=int, default=250000)
    parser.add_argument("--languages", nargs="+", default=sorted(DEFAULT_LANGUAGES))
    return parser.parse_args()


if __name__ == "__main__":
    build_index(parse_args())
