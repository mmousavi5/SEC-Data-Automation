from __future__ import annotations

import atexit
import re

from playwright.sync_api import sync_playwright

from .config import settings
from .models import FilingJob

_playwright = None
_browser = None


def _get_browser():
    """One Chromium instance per worker process, reused across every job that process
    handles. ProcessPoolExecutor reuses worker processes across submitted tasks, so
    launching a fresh browser per filing would pay startup cost repeatedly for nothing —
    a page (opened and closed per job below) is cheap; a browser process is not."""
    global _playwright, _browser
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch()
    return _browser


@atexit.register
def _shutdown_browser() -> None:
    if _browser is not None:
        _browser.close()
    if _playwright is not None:
        _playwright.stop()


def _safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


def convert_to_pdf(job: FilingJob):
    """Runs inside a process-pool worker. Takes and returns plain data (a FilingJob and a
    Path) so it can cross the process boundary without needing shared memory."""
    raw_path = job.raw_path or (settings.raw_dir / f"{job.cik}_{job.accession}.htm")
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = settings.pdf_dir / f"{_safe_filename(job.company_name)}_{job.fiscal_year}_10-K.pdf"

    page = _get_browser().new_page()
    try:
        page.goto(raw_path.resolve().as_uri())
        page.pdf(path=str(pdf_path))
    finally:
        page.close()

    return pdf_path
