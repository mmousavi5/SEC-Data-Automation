from typing import Protocol

from .models import Company


class CompanyProvider(Protocol):
    def list_companies(self) -> list[Company]: ...


class LocalFileProvider:
    def __init__(self, path):
        self._path = path

    def list_companies(self) -> list[Company]:
        raise NotImplementedError


def get_provider(name: str) -> CompanyProvider:
    raise NotImplementedError
