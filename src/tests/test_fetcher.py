import queue

import pytest
import requests

from sec_fetcher import edgar_client
from sec_fetcher.config import settings
from sec_fetcher.fetcher import fetch_company
from sec_fetcher.models import Company, Filing, FilingJob, Status
from sec_fetcher.state_store import LocalFileStateStore

CIK = "0000320193"
ACCESSION = "0000320193-24-000123"

FILING = Filing(
    accession=ACCESSION,
    primary_document="aapl-20240928.htm",
    fiscal_year="2024",
    form="10-K",
)


def make_company():
    return Company(name="Apple Inc", ticker="AAPL", cik=CIK)


def make_job():
    return FilingJob(cik=CIK, accession=ACCESSION, company_name="Apple Inc", fiscal_year="2024")


def test_successful_fetch_marks_fetched_and_queues_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "raw_dir", tmp_path)
    monkeypatch.setattr(edgar_client, "resolve_cik", lambda company: CIK)
    monkeypatch.setattr(edgar_client, "list_recent_filings", lambda cik, form_type, limit: [FILING])
    monkeypatch.setattr(
        edgar_client, "download_filing_document", lambda cik, filing: b"<html></html>"
    )

    state_store = LocalFileStateStore(tmp_path / "state.jsonl")
    job_queue = queue.Queue()

    fetch_company(make_company(), state_store, job_queue)

    assert state_store.get_status(make_job()) == Status.FETCHED
    assert job_queue.qsize() == 1

    queued_job = job_queue.get_nowait()
    assert queued_job.key == make_job().key
    assert queued_job.raw_path == tmp_path / f"{CIK}_{ACCESSION}.htm"
    assert queued_job.raw_path.read_bytes() == b"<html></html>"


@pytest.mark.parametrize("status", [Status.FETCHED, Status.CONVERTED])
def test_already_processed_job_is_skipped(tmp_path, monkeypatch, status):
    def unexpected_download(cik, filing):
        raise AssertionError("download_filing_document should not be called")

    monkeypatch.setattr(edgar_client, "resolve_cik", lambda company: CIK)
    monkeypatch.setattr(edgar_client, "list_recent_filings", lambda cik, form_type, limit: [FILING])
    monkeypatch.setattr(edgar_client, "download_filing_document", unexpected_download)

    state_store = LocalFileStateStore(tmp_path / "state.jsonl")
    state_store.set_status(make_job(), status)
    job_queue = queue.Queue()

    fetch_company(make_company(), state_store, job_queue)

    assert state_store.get_status(make_job()) == status
    assert job_queue.qsize() == 0


def test_persistent_download_failure_retries_max_plus_one_then_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_job_retries", 2)
    monkeypatch.setattr(edgar_client, "resolve_cik", lambda company: CIK)
    monkeypatch.setattr(edgar_client, "list_recent_filings", lambda cik, form_type, limit: [FILING])

    calls = []

    def always_fails(cik, filing):
        calls.append(1)
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(edgar_client, "download_filing_document", always_fails)

    state_store = LocalFileStateStore(tmp_path / "state.jsonl")
    job_queue = queue.Queue()

    fetch_company(make_company(), state_store, job_queue)

    # settings.max_job_retries=2 means retries land on 1, 2, 3 — the job is only
    # dead-lettered once retries > max_job_retries, i.e. after max_job_retries + 1
    # actual download attempts, not max_job_retries.
    assert len(calls) == settings.max_job_retries + 1
    assert state_store.get_status(make_job()) == Status.FAILED
    assert job_queue.qsize() == 0
