from sec_fetcher.models import FilingJob, Status
from sec_fetcher.state_store import LocalFileStateStore


def make_job(accession="0000320193-24-000123"):
    return FilingJob(
        cik="0000320193", accession=accession, company_name="Apple Inc", fiscal_year="2024"
    )


def test_unknown_job_has_no_status(tmp_path):
    store = LocalFileStateStore(tmp_path / "state.jsonl")
    assert store.get_status(make_job()) is None


def test_set_status_is_visible_immediately(tmp_path):
    store = LocalFileStateStore(tmp_path / "state.jsonl")
    job = make_job()

    store.set_status(job, Status.PENDING)
    assert store.get_status(job) == Status.PENDING

    store.set_status(job, Status.FETCHED)
    assert store.get_status(job) == Status.FETCHED


def test_restart_replays_the_ledger_from_disk(tmp_path):
    path = tmp_path / "state.jsonl"
    job = make_job()

    first_run = LocalFileStateStore(path)
    first_run.set_status(job, Status.FETCHED)

    # Simulate a crash + restart: a brand new store instance over the same file.
    second_run = LocalFileStateStore(path)
    assert second_run.get_status(job) == Status.FETCHED
    assert second_run.list_pending() == [job]


def test_converted_jobs_are_not_pending(tmp_path):
    store = LocalFileStateStore(tmp_path / "state.jsonl")
    job = make_job()

    store.set_status(job, Status.FETCHED)
    store.set_status(job, Status.CONVERTED)

    assert store.list_pending() == []
