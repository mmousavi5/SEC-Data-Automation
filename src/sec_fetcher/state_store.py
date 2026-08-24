from typing import Protocol

from .models import FilingJob, Status


class StateStore(Protocol):
    def get_status(self, job: FilingJob) -> Status | None: ...
    def set_status(self, job: FilingJob, status: Status) -> None: ...
    def list_pending(self) -> list[FilingJob]: ...


class LocalFileStateStore:
    def __init__(self, path):
        self._path = path

    def get_status(self, job: FilingJob) -> Status | None:
        raise NotImplementedError

    def set_status(self, job: FilingJob, status: Status) -> None:
        raise NotImplementedError

    def list_pending(self) -> list[FilingJob]:
        raise NotImplementedError
