# Question log — SEC-Data-Automation session (2026-08-24)

1. What is the exact JSON shape of the `data.sec.gov/submissions/{cik}.json` endpoint, specifically the `filings.recent` arrays?

2. Getting a 403 from the SEC API — what auth method are they requiring?

3. With a CIK and an accession number, what is the SEC URL pattern for downloading the actual filing document from their archives?

4. Is calling `load_ledger()` fresh inside every thread call safe, or is there a race condition to worry about? (re: `main.py`)

5. Write pytest tests for `fetch_company` in `src/sec_fetcher/fetcher.py`, following `tests/test_edgar_client.py`'s style — plain assert, monkeypatch `edgar_client.resolve_cik` / `list_recent_filings` / `download_filing_document`, use a real `LocalFileStateStore(tmp_path / 'state.jsonl')` instead of mocking the ledger.

6. Write the log of all my questions in a file.