# SEC-Data-Automation

Downloads 10-K filings for a list of companies from SEC EDGAR and converts each one to a
PDF. A local ledger tracks every filing through the pipeline, so a restart after a crash
or a `Ctrl-C` resumes only the work that wasn't finished.

## How it works

The pipeline has two stages, connected by a status ledger:

1. **Fetch.** For each company, resolve its CIK (from `companies.json`, or by looking it
   up in SEC's bulk ticker file if missing), find its most recent filing of
   `SEC_FETCHER_FORM_TYPE`, and download the raw HTML document. Runs on a thread pool
   (`SEC_FETCHER_FETCH_WORKERS` workers) since the work is network-bound, and every
   outbound request goes through a shared rate limiter capped at
   `SEC_FETCHER_RATE_LIMIT_PER_SECOND` requests/second, in line with SEC's fair-access
   rules. A failed download retries up to `SEC_FETCHER_MAX_JOB_RETRIES` times before the
   filing is marked `failed`; a company whose CIK can't be resolved or has no filings
   listed is logged and skipped, not retried.
2. **Convert.** Each fetched filing is rendered to PDF with a headless Chromium instance
   (Playwright). Runs on a process pool, since PDF rendering is CPU-bound and each worker
   process reuses one browser instance across every job it handles. A failed conversion
   retries up to `SEC_FETCHER_MAX_JOB_RETRIES` times before being marked `failed`.

`LocalFileStateStore` (`src/sec_fetcher/state_store.py`) is the ledger: an append-only
JSONL file (`SEC_FETCHER_STATE_PATH`) where each line records a filing's status
(`pending` → `fetched` → `converted`, or `failed`). On startup, `main.py` replays this
file and re-queues anything left in `fetched` state before fetching anything new, so a
filing that was downloaded but never converted isn't re-downloaded. The fetch stage also
checks the ledger per filing: a company whose latest 10-K is already `fetched`,
`converted`, or `failed` from a previous run is skipped rather than re-downloaded.

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

2. Copy the example environment file and set a real User-Agent:

   ```
   cp .env.example .env
   ```

   SEC EDGAR requires a User-Agent that identifies the requester; edit
   `SEC_FETCHER_USER_AGENT` in `.env` before running — requests sent with the placeholder
   value are liable to be rate-limited or blocked. Every other setting already has a
   working default (see **Configuration** below). To use the sample company list included
   in the repo root instead of the default `data/companies.json`, also set:

   ```
   SEC_FETCHER_COMPANIES_PATH=companies.json
   ```

3. Run the pipeline:

   ```
   PYTHONPATH=src python -m sec_fetcher.main
   ```

   This fetches each company's most recent 10-K and writes a PDF per filing to
   `SEC_FETCHER_PDF_DIR` (`data/pdf` by default).

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
| `fetcher.py` | Per-company fetch step that ties `edgar_client` calls to the state ledger. |
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
