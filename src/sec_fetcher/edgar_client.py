from .models import Company, Filing


def resolve_cik(company: Company) -> str:
    raise NotImplementedError


def list_recent_filings(cik: str, form_type: str, limit: int) -> list[Filing]:
    raise NotImplementedError


def download_filing_document(cik: str, filing: Filing) -> bytes:
    raise NotImplementedError
