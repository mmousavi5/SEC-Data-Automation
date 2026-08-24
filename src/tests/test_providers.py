import json

import pytest

from sec_fetcher.providers import LocalFileProvider, get_provider


def test_local_file_provider_reads_companies(tmp_path):
    path = tmp_path / "companies.json"
    path.write_text(json.dumps([{"name": "Apple Inc", "ticker": "AAPL", "cik": "0000320193"}]))

    companies = LocalFileProvider(path).list_companies()

    assert len(companies) == 1
    assert companies[0].name == "Apple Inc"
    assert companies[0].cik == "0000320193"


def test_local_file_provider_allows_missing_cik(tmp_path):
    path = tmp_path / "companies.json"
    path.write_text(json.dumps([{"name": "Some New Company", "ticker": "SNC"}]))

    companies = LocalFileProvider(path).list_companies()

    assert companies[0].cik is None


def test_get_provider_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_provider("some_provider_that_does_not_exist")
