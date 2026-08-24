from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .models import FilingJob, Status


class StateStore(Protocol):
    def get_status(self, job: FilingJob) -> Status | None: ...
    def set_status(self, job: FilingJob, status: Status) -> None: ...
    def list_pending(self) -> list[FilingJob]: ...


class LocalFileStateStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._latest: dict[tuple[str, str], dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                self._latest[(row["cik"], row["accession"])] = row

    def get_status(self, job: FilingJob) -> Status | None:
        row = self._latest.get(job.key)
        return Status(row["status"]) if row else None

    def set_status(self, job: FilingJob, status: Status) -> None:
        row = {
            "cik": job.cik,
            "accession": job.accession,
            "company_name": job.company_name,
            "fiscal_year": job.fiscal_year,
            "status": status.value,
            "retries": job.retries,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            self._latest[job.key] = row

    def list_pending(self) -> list[FilingJob]:
        jobs = []
        for row in self._latest.values():
            if row["status"] == Status.FETCHED.value:
                jobs.append(
                    FilingJob(
                        cik=row["cik"],
                        accession=row["accession"],
                        company_name=row["company_name"],
                        fiscal_year=row["fiscal_year"],
                        retries=row.get("retries", 0),
                    )
                )
        return jobs
