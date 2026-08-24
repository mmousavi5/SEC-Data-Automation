# SEC-Data-Automation

Downloads 10-K filings for a list of companies from SEC EDGAR and converts each one to a
PDF. A local ledger tracks every filing through the pipeline, so a restart after a crash
or a `Ctrl-C` resumes only the work that wasn't finished.

**Current status:** the fetch stage is not implemented yet. `fetcher.fetch_company()`
(`src/sec_fetcher/fetcher.py`) is a stub that raises `NotImplementedError` — running the
pipeline today loads the company list and then fails on the first company. The pieces it
needs (`resolve_cik`, `list_recent_filings`, `download_filing_document` in
`edgar_client.py`) exist and are usable; they're just not wired together yet.

## How it works

The pipeline has two stages, connected by a status ledger:

1. **Fetch.** For each company, resolve its CIK (from `companies.json`, or by looking it
   up in SEC's bulk ticker file if missing), find its most recent filing of
   `SEC_FETCHER_FORM_TYPE`, and download the raw HTML document. Runs on a thread pool
   (`SEC_FETCHER_FETCH_WORKERS` workers) since the work is network-bound, and every
   outbound request goes through a shared rate limiter capped at
   `SEC_FETCHER_RATE_LIMIT_PER_SECOND` requests/second, in line with SEC's fair-access
   rules.
2. **Convert.** Each fetched filing is rendered to PDF with a headless Chromium instance
   (Playwright). Runs on a process pool, since PDF rendering is CPU-bound and each worker
   process reuses one browser instance across every job it handles. A failed conversion
   retries up to `SEC_FETCHER_MAX_JOB_RETRIES` times before being marked `failed`.

`LocalFileStateStore` (`src/sec_fetcher/state_store.py`) is the ledger: an append-only
JSONL file (`SEC_FETCHER_STATE_PATH`) where each line records a filing's status
(`pending` → `fetched` → `converted`, or `failed`). On startup, `main.py` replays this
file and re-queues anything left in `fetched` state before fetching anything new, so a
filing that was downloaded but never converted isn't re-downloaded.

Within a single run, fetched jobs hand off to the convert stage through an in-memory
`queue.Queue` (`main.py:56`) — a stand-in for a real message broker. It works because
fetch and convert both run in the same process for the lifetime of one `run()` call; it
does not survive a restart on its own, which is why the ledger (not the queue) is the
source of truth for resuming work.

Which company list is used is decided by `SEC_FETCHER_COMPANY_PROVIDER`. Today the only
implementation is `local_file` (reads `SEC_FETCHER_COMPANIES_PATH`); `get_provider()` in
`providers.py` is the extension point for adding others.

## Getting started

1. Install dependencies:

   ```
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Copy the example environment file and adjust it if needed:

   ```
   cp .env.example .env
   ```

   The defaults write all data under `./data` and read companies from
   `data/companies.json` — copy or point `SEC_FETCHER_COMPANIES_PATH` at the
   `companies.json` in the repo root to use the sample list (Apple, Microsoft, Amazon).

3. Set a real `SEC_FETCHER_USER_AGENT` in `.env`. SEC EDGAR requires a descriptive
   User-Agent identifying the requester (for example `"Your Name your@email.com"`);
   requests with the placeholder value are liable to be rate-limited or blocked.

4. Run the pipeline:

   ```
   PYTHONPATH=src python -m sec_fetcher.main
   ```

   Until the fetch stage is implemented (see **Current status** above), this loads the
   company list and then raises `NotImplementedError` on the first company.

## Configuration

All settings are environment variables with a `SEC_FETCHER_` prefix, loaded from `.env`
(see `src/sec_fetcher/config.py`).

| Variable | Default | Description |
|---|---|---|
| `SEC_FETCHER_COMPANY_PROVIDER` | `local_file` | Which `CompanyProvider` implementation supplies the company list. |
| `SEC_FETCHER_FILINGS_PER_COMPANY` | `1` | How many of the most recent matching filings to fetch per company. |
| `SEC_FETCHER_FORM_TYPE` | `10-K` | SEC form type to filter for. |
| `SEC_FETCHER_RATE_LIMIT_PER_SECOND` | `8` | Cap on outbound requests to SEC EDGAR, shared across all fetch workers. |
| `SEC_FETCHER_MAX_JOB_RETRIES` | `3` | Retries for a failed PDF conversion before the job is marked `failed`. |
| `SEC_FETCHER_FETCH_WORKERS` | `4` | Thread pool size for the fetch stage. |
| `SEC_FETCHER_USER_AGENT` | `"A Test Project dev@example.com"` | Sent on every request to SEC EDGAR. Replace with your own contact info. |
| `SEC_FETCHER_COMPANIES_PATH` | `data/companies.json` | Company list read by the `local_file` provider. |
| `SEC_FETCHER_RAW_DIR` | `data/raw` | Where downloaded filing HTML is written. |
| `SEC_FETCHER_PDF_DIR` | `data/pdf` | Where converted PDFs are written. |
| `SEC_FETCHER_STATE_PATH` | `data/state.jsonl` | Path to the status ledger. |
| `SEC_FETCHER_TICKER_CACHE_PATH` | `data/.ticker_cache.json` | Disk cache of SEC's ticker → CIK bulk file. |
| `SEC_FETCHER_TICKER_CACHE_TTL_SECONDS` | `86400` | How long the ticker cache is trusted before it's re-downloaded. |

## Project layout

| Module | Responsibility |
|---|---|
| `main.py` | Orchestrates a run: loads companies, fetches on a thread pool, converts on a process pool. |
| `edgar_client.py` | All outbound calls to SEC EDGAR — CIK resolution, filing lookup, document download, rate limiting. |
| `fetcher.py` | Per-company fetch step that ties `edgar_client` calls to the state ledger. Currently a stub. |
| `converter.py` | Renders a fetched filing's HTML to PDF via headless Chromium. |
| `providers.py` | `CompanyProvider` implementations — where the company list comes from. |
| `state_store.py` | The JSONL status ledger (`LocalFileStateStore`) that makes a restart resumable. |
| `models.py` | Shared data types: `Company`, `Filing`, `FilingJob`, `Status`. |
| `config.py` | Environment-backed settings (`Settings`, loaded from `.env`). |

## Running tests

```
pip install -r requirements.txt
pytest
```
