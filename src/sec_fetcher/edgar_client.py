from __future__ import annotations

import json
import threading
import time

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings
from .models import Company, Filing

_TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{document}"


class _RateLimiter:
    """Caps outbound requests to settings.rate_limit_per_second across all threads."""

    def __init__(self, per_second: int):
        self._interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._interval:
                time.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()


_limiter = _RateLimiter(settings.rate_limit_per_second)
_ticker_cache: dict[str, str] | None = None

_session = requests.Session()
_session.headers.update({"User-Agent": settings.user_agent})


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(requests.RequestException),
)
def _get(url: str) -> requests.Response:
    """Rate limit + retry, wrapped around every outbound call — a cross-cutting concern
    that has no business living inside the functions that just want a URL's contents.
    Uses a shared Session so repeated calls to the same host reuse one TCP+TLS connection
    instead of paying a fresh handshake every time."""
    _limiter.wait()
    resp = _session.get(url, timeout=15)
    resp.raise_for_status()
    return resp


def _load_ticker_cache() -> dict[str, str]:
    """In-memory for the rest of this process, and persisted to disk across processes —
    company_tickers.json is several MB and changes rarely, so a run that resolves any
    company by ticker shouldn't have to re-download it every time."""
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache

    cache_path = settings.ticker_cache_path
    if cache_path.exists():
        age_seconds = time.time() - cache_path.stat().st_mtime
        if age_seconds < settings.ticker_cache_ttl_seconds:
            _ticker_cache = json.loads(cache_path.read_text())
            return _ticker_cache

    data = _get(_TICKER_LOOKUP_URL).json()
    _ticker_cache = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in data.values()}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(_ticker_cache))

    return _ticker_cache


def resolve_cik(company: Company) -> str:
    """Adapter: callers get a CIK for a company regardless of whether the provider already
    knew it or SEC's bulk lookup file (company_tickers.json) had to fill it in."""
    if company.cik:
        return str(company.cik).zfill(10)
    cik = _load_ticker_cache().get(company.ticker.upper())
    if cik is None:
        raise ValueError(f"could not resolve CIK for {company.name} ({company.ticker})")
    return cik


def list_recent_filings(cik: str, form_type: str, limit: int) -> list[Filing]:
    """SEC's submissions API returns filings newest-first, so the first `limit` matches
    of the requested form are the `limit` most recent filings of that type."""
    data = _get(_SUBMISSIONS_URL.format(cik=cik)).json()
    recent = data["filings"]["recent"]
    filing_fields = zip(
        recent["form"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        recent["reportDate"],
        strict=True,
    )
    matches = []
    for form, accession, primary_document, report_date in filing_fields:
        if form == form_type:
            fiscal_year = report_date[:4] if report_date else "unknown"
            matches.append(
                Filing(
                    accession=accession,
                    primary_document=primary_document,
                    fiscal_year=fiscal_year,
                    form=form,
                )
            )
        if len(matches) >= limit:
            break
    return matches


def download_filing_document(cik: str, filing: Filing) -> bytes:
    url = _ARCHIVES_URL.format(
        cik_no_zeros=str(int(cik)),
        accession_no_dashes=filing.accession.replace("-", ""),
        document=filing.primary_document,
    )
    return _get(url).content
