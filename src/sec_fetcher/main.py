from __future__ import annotations

import concurrent.futures as cf
import logging
import queue

from playwright.sync_api import Error as PlaywrightError

from . import converter, fetcher
from .config import settings
from .models import FilingJob, Status
from .providers import get_provider
from .state_store import LocalFileStateStore, StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sec_fetcher")


def run_conversions(jobs: list[FilingJob], state_store: StateStore) -> None:
    """Consumes a batch of fetched jobs on a process pool, retrying failures up to
    settings.max_job_retries before dead-lettering them."""
    with cf.ProcessPoolExecutor() as pool:
        futures = {pool.submit(converter.convert_to_pdf, job): job for job in jobs}
        while futures:
            done, _ = cf.wait(futures, return_when=cf.FIRST_COMPLETED)
            for future in done:
                job = futures.pop(future)
                try:
                    pdf_path = future.result()
                    job.pdf_path = pdf_path
                    state_store.set_status(job, Status.CONVERTED)
                    logger.info("converted %s %s -> %s", job.cik, job.accession, pdf_path)
                except (PlaywrightError, OSError):
                    job.retries += 1
                    if job.retries > settings.max_job_retries:
                        state_store.set_status(job, Status.FAILED)
                        logger.error(
                            "dead-lettered %s %s after %d retries (convert)",
                            job.cik,
                            job.accession,
                            job.retries,
                        )
                    else:
                        logger.warning(
                            "convert failed for %s %s, retry %d/%d",
                            job.cik,
                            job.accession,
                            job.retries,
                            settings.max_job_retries,
                        )
                        futures[pool.submit(converter.convert_to_pdf, job)] = job


def run() -> None:
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)

    state_store = LocalFileStateStore(settings.state_path)
    job_queue: queue.Queue[FilingJob] = queue.Queue()  # stands in for a real broker — see README

    # Resume anything a previous, interrupted run had fetched but never converted, before
    # this run adds anything new — that's what makes "request 8765 failed" a non-event.
    for job in state_store.list_pending():
        job.raw_path = settings.raw_dir / f"{job.cik}_{job.accession}.htm"
        job_queue.put(job)

    companies = get_provider(settings.company_provider).list_companies()
    logger.info("loaded %d companies from provider=%r", len(companies), settings.company_provider)

    with cf.ThreadPoolExecutor(max_workers=settings.fetch_workers) as pool:
        list(pool.map(lambda c: fetcher.fetch_company(c, state_store, job_queue), companies))

    jobs = []
    while not job_queue.empty():
        jobs.append(job_queue.get())

    if not jobs:
        logger.info("nothing new to convert")
        return

    run_conversions(jobs, state_store)
    logger.info("done")


if __name__ == "__main__":
    run()
