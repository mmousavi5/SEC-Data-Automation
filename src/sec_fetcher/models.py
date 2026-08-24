from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Status(str, StrEnum):
    PENDING = "pending"
    FETCHED = "fetched"
    CONVERTED = "converted"
    FAILED = "failed"


@dataclass
class Company:
    """One entry from a CompanyProvider. cik is optional — edgar_client fills it in if missing."""

    name: str
    ticker: str
    cik: str | None = None


@dataclass
class Filing:
    """One row out of SEC's per-company filing list."""

    accession: str
    primary_document: str
    fiscal_year: str
    form: str


@dataclass
class FilingJob:
    """One unit of work, tracked end to end through fetch -> convert -> done/failed."""

    cik: str
    accession: str
    company_name: str
    fiscal_year: str
    retries: int = 0
    raw_path: Path | None = None
    pdf_path: Path | None = None

    @property
    def key(self) -> tuple[str, str]:
        """The permanent, SEC-assigned identity of a filing — what the ledger is keyed on."""
        return (self.cik, self.accession)
