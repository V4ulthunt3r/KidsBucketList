# Kids Bucket List Book Catalog

`books.sqlite` is the static book catalog used by the iOS app.
`manifest.json` points the app to the current database version and includes
the SHA-256 checksum.

Generate it from the monthly OpenLibrary dumps:

```bash
python3 scripts/build-openlibrary-book-index.py \
  --authors-dump ~/Downloads/ol_dump_authors_latest.txt.gz \
  --editions-dump ~/Downloads/ol_dump_editions_latest.txt.gz \
  --database-output data/books/books.sqlite \
  --manifest-output data/books/manifest.json \
  --database-url https://v4ulthunt3r.github.io/KidsBucketList/data/books/books.sqlite \
  --version 2026-04 \
  --limit 220000
```

Source dumps: https://openlibrary.org/developers/dumps
