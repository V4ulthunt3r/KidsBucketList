# Kids Bucket List Book Catalog

`manifest.json` is the small GitHub Pages entrypoint used by the iOS app.
The SQLite catalog itself is published as a GitHub Release asset because it is
larger than the practical GitHub Pages/repository file-size range.

Generate it from the monthly OpenLibrary dumps:

```bash
python3 scripts/build-openlibrary-book-index.py \
  --authors-dump ~/Downloads/ol_dump_authors_latest.txt.gz \
  --editions-dump ~/Downloads/ol_dump_editions_latest.txt.gz \
  --database-output /tmp/books-2026-03-31-large.sqlite \
  --manifest-output data/books/manifest.json \
  --database-url https://github.com/V4ulthunt3r/KidsBucketList/releases/download/books-2026-03-31-large/books-2026-03-31-large.sqlite \
  --version 2026-03-31-large \
  --limit 1000000
```

The default language filter is German and English (`de`, `deu`, `ger`, `en`,
`eng`). Add `--family-only` only when generating a smaller family-focused
catalog.

Source dumps: https://openlibrary.org/developers/dumps
