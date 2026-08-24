from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEC_FETCHER_")

    company_provider: str = "local_file"
    filings_per_company: int = 1
    form_type: str = "10-K"
    rate_limit_per_second: int = 8
    max_job_retries: int = 3
    fetch_workers: int = 4
    user_agent: str = "A Test Project dev@example.com"

    companies_path: Path = Path("data/companies.json")
    raw_dir: Path = Path("data/raw")
    pdf_dir: Path = Path("data/pdf")
    state_path: Path = Path("data/state.jsonl")
    ticker_cache_path: Path = Path("data/.ticker_cache.json")
    ticker_cache_ttl_seconds: int = 86400


settings = Settings()
