from __future__ import annotations

import json
from typing import Protocol
from pathlib import Path

from .config import settings
from .models import Company


class CompanyProvider(Protocol):
    def list_companies(self) -> list[Company]: ...


class LocalFileProvider:
    def __init__(self, path: Path) -> None:
        self._path = path

    def list_companies(self) -> list[Company]:
        with open(self._path) as f:
            rows = json.load(f)
        return [Company(name=r["name"], ticker=r["ticker"], cik=r.get("cik")) for r in rows]


def get_provider(name: str) -> CompanyProvider:
    """One string in config picks the implementation; callers never construct one directly."""
    if name == "local_file":
        return LocalFileProvider(settings.companies_path)
    raise ValueError(f"unknown company_provider: {name!r}")
