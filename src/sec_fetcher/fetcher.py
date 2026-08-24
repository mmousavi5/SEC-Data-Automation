from .models import Company
from .state_store import StateStore


def fetch_company(company: Company, state_store: StateStore, job_queue) -> None:
    raise NotImplementedError
