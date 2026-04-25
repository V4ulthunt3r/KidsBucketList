# Kids Bucket List Book Catalog

`search-index.json` is the static book catalog used by the iOS app.

Generate it from the monthly OpenLibrary dumps:

```bash
python3 scripts/build-openlibrary-book-index.py \
  --authors-dump ~/Downloads/ol_dump_authors_latest.txt.gz \
  --editions-dump ~/Downloads/ol_dump_editions_latest.txt.gz \
  --output data/books/search-index.json \
  --limit 5000
```

Source dumps: https://openlibrary.org/developers/dumps
