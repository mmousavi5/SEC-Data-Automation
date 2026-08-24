import json
import os
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEC_FETCHER_")

    user_agent: str = "A Test Project dev@example.com"
    state_path: str = "state.jsonl"
    companies_path: str = "companies.json"


settings = Settings()


def load_companies(path):
    with open(path) as f:
        rows = json.load(f)
    return [(row["name"], row["cik"]) for row in rows]


COMPANIES = load_companies(settings.companies_path)


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


def convert_to_pdf(raw_path, pdf_path):
    # Naive on purpose: a fresh browser per call. A later step reuses one instead.
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(Path(raw_path).resolve().as_uri())
        page.pdf(path=pdf_path)
        browser.close()


status_by_key = load_ledger()

for name, cik in COMPANIES:
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(submissions_url, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    recent = response.json()["filings"]["recent"]

    accession = None
    document = None
    filing_fields = zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"], strict=True
    )
    for form, acc, doc in filing_fields:
        if form == "10-K":
            accession = acc
            document = doc
            break

    if accession is None:
        print(f"no 10-K found for {name}, skipping")
        continue

    key = (cik, accession)
    status = status_by_key.get(key)
    raw_path = f"{cik}_{accession}.htm"
    pdf_path = f"{cik}_{accession}.pdf"

    if status == "converted":
        print(f"{name} is already converted, skipping")
        continue

    if status != "fetched":
        # Nothing usable on disk yet, so fetch first.
        try:
            cik_no_zeros = str(int(cik))
            accession_no_dashes = accession.replace("-", "")
            document_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{document}"
            )
            document_response = requests.get(
                document_url, headers={"User-Agent": settings.user_agent}
            )
            document_response.raise_for_status()

            with open(raw_path, "wb") as f:
                f.write(document_response.content)

            record_status(cik, accession, "fetched")
            status_by_key[key] = "fetched"
            print(f"fetched {name} -> {raw_path}")

        except requests.RequestException:
            record_status(cik, accession, "failed")
            status_by_key[key] = "failed"
            print(f"failed to fetch {name}, recorded as failed")
            continue

    try:
        convert_to_pdf(raw_path, pdf_path)
        record_status(cik, accession, "converted")
        status_by_key[key] = "converted"
        print(f"converted {name} -> {pdf_path}")
    except Exception:
        record_status(cik, accession, "failed")
        status_by_key[key] = "failed"
        print(f"failed to convert {name}, recorded as failed")
