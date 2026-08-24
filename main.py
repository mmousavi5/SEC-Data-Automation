import json
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEC_FETCHER_")

    user_agent: str = "A Test Project dev@example.com"
    state_path: str = "state.jsonl"
    companies_path: str = "companies.json"
    fetch_workers: int = 4


settings = Settings()


def load_companies(path):
    with open(path) as f:
        rows = json.load(f)
    return [(row["name"], row["cik"]) for row in rows]


def load_ledger():
    # Replay the log; the last line for a key is its current status.
    status_by_key = {}
    if os.path.exists(settings.state_path):
        with open(settings.state_path) as f:
            for line in f:
                record = json.loads(line)
                key = (record["cik"], record["accession"])
                status_by_key[key] = record["status"]
    return status_by_key


def record_status(cik, accession, status):
    # Always append, never rewrite, so a crash can only cost the newest line.
    with open(settings.state_path, "a") as f:
        f.write(json.dumps({"cik": cik, "accession": accession, "status": status}) + "\n")


def find_latest_10k(cik):
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(submissions_url, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    recent = response.json()["filings"]["recent"]

    filing_fields = zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"], strict=True
    )
    for form, acc, doc in filing_fields:
        if form == "10-K":
            return acc, doc
    return None, None


def fetch_company(name, cik):
    # Runs on the thread pool. Leaves this company "fetched" or "failed" in the
    # ledger, or does nothing if it's already past that point.
    accession, document = find_latest_10k(cik)
    if accession is None:
        print(f"no 10-K found for {name}, skipping")
        return

    status = load_ledger().get((cik, accession))
    if status in ("fetched", "converted"):
        print(f"{name} is already {status}, skipping")
        return

    try:
        cik_no_zeros = str(int(cik))
        accession_no_dashes = accession.replace("-", "")
        document_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{document}"
        )
        document_response = requests.get(document_url, headers={"User-Agent": settings.user_agent})
        document_response.raise_for_status()

        raw_path = f"{cik}_{accession}.htm"
        with open(raw_path, "wb") as f:
            f.write(document_response.content)

        record_status(cik, accession, "fetched")
        print(f"fetched {name} -> {raw_path}")

    except requests.RequestException:
        record_status(cik, accession, "failed")
        print(f"failed to fetch {name}, recorded as failed")


def convert_job(cik, accession):
    # Runs on the process pool, in a separate process — it can't see fetch_company's
    # variables, so it recomputes the same file paths from just (cik, accession).
    raw_path = f"{cik}_{accession}.htm"
    pdf_path = f"{cik}_{accession}.pdf"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(Path(raw_path).resolve().as_uri())
            page.pdf(path=pdf_path)
            browser.close()
        record_status(cik, accession, "converted")
        print(f"converted {cik} {accession} -> {pdf_path}")
    except Exception:
        record_status(cik, accession, "failed")
        print(f"failed to convert {cik} {accession}, recorded as failed")


if __name__ == "__main__":
    companies = load_companies(settings.companies_path)
    names = [name for name, cik in companies]
    ciks = [cik for name, cik in companies]

    # Phase 1: fetch everyone concurrently. I/O-bound, so threads give real parallelism.
    with ThreadPoolExecutor(max_workers=settings.fetch_workers) as pool:
        list(pool.map(fetch_company, names, ciks))

    # Phase 2: convert everyone that's fetched, concurrently. CPU-bound rendering
    # needs real processes, not threads, to actually run in parallel.
    status_by_key = load_ledger()
    jobs = [key for key, status in status_by_key.items() if status == "fetched"]
    job_ciks = [cik for cik, accession in jobs]
    job_accessions = [accession for cik, accession in jobs]

    with ProcessPoolExecutor() as pool:
        list(pool.map(convert_job, job_ciks, job_accessions))
