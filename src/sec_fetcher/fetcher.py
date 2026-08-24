from __future__ import annotations

import logging
import queue

import requests

from . import edgar_client
from .config import settings
from .models import Company, FilingJob, Status
from .state_store import StateStore

logger = logging.getLogger(__name__)


def fetch_company(
    company: Company, state_store: StateStore, job_queue: queue.Queue[FilingJob]
) -> None:
    try:
        cik = edgar_client.resolve_cik(company)
    except (requests.RequestException, ValueError, OSError):
        logger.exception("could not resolve CIK for %s", company.name)
        return

    try:
        filings = edgar_client.list_recent_filings(
            cik, settings.form_type, settings.filings_per_company
        )
    except (requests.RequestException, KeyError):
        logger.exception("could not list filings for %s (cik=%s)", company.name, cik)
        return

    for filing in filings:
        job = FilingJob(
            cik=cik,
            accession=filing.accession,
            company_name=company.name,
            fiscal_year=filing.fiscal_year,
        )

        if state_store.get_status(job) is not None:
            continue  # already fetched (or converted, or dead-lettered) on a previous run

        state_store.set_status(job, Status.PENDING)

        while True:
            try:
                html = edgar_client.download_filing_document(cik, filing)
                raw_path = settings.raw_dir / f"{cik}_{filing.accession}.htm"
                raw_path.write_bytes(html)
                job.raw_path = raw_path
                state_store.set_status(job, Status.FETCHED)
                job_queue.put(job)
                logger.info(
                    "fetched %s %s (FY%s)", company.name, filing.accession, filing.fiscal_year
                )
                break
            except (requests.RequestException, OSError):
                job.retries += 1
                if job.retries > settings.max_job_retries:
                    logger.exception(
                        "dead-lettered %s %s after %d retries (fetch)",
                        company.name,
                        filing.accession,
                        job.retries,
                    )
                    state_store.set_status(job, Status.FAILED)
                    break
                logger.warning(
                    "fetch failed for %s %s, retry %d/%d",
                    company.name,
                    filing.accession,
                    job.retries,
                    settings.max_job_retries,
                )
