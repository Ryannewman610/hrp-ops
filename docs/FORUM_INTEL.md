# Forum Intel Ingestion (Manual, No Scraping)

This workflow is local-file only. It does not fetch or scrape anything from the web.

## Input Folder

- Drop files into: `inputs/forums/raw/`
- Supported file types:
  - `.txt`
  - `.md`
  - `.html`

## Optional URL Header

If you have the thread URL, place it on the first line:

```text
URL: https://example.com/thread/123
```

## Optional Metadata Headers

You can also include:

```text
Author: SomeUser
Date: 2026-02-16
```

## Parse Command

```powershell
py scripts/10_parse_forum_notes.py
```

## Outputs

- Claims JSONL: `outputs/forums/forum_claims.jsonl`
  - One JSON object per claim
  - Fields: `topic`, `claim`, `source_url`, `source_file`, `author`, `date`, `confidence`
  - Default `confidence` is `Low`
- Summary markdown: `outputs/forums/FORUM_CLAIMS_SUMMARY.md`
  - Grouped by topic

## Empty Input Behavior

If `inputs/forums/raw/` has no supported files, the script still succeeds and writes:

- an empty JSONL file
- a summary markdown noting no claims were parsed
