"""Dashboard settings.

Mirrors the worker/investigator pattern: a single DSN env var for local dev,
or individual parts for AWS where the RDS-managed secret delivers
user+password separately from the host.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PGSCP_", env_file=None, extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    # Postgres -- read-only access. Same DSN-from-parts pattern as worker.
    db_dsn: str = "postgresql+psycopg://pgscp:pgscp@postgres:5432/pgscp"
    db_user: str = ""
    db_password: str = ""
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "pgscp"

    # Investigator's feedback API. POSTs go here when a user labels an
    # investigation as correct/incorrect.
    investigator_feedback_url: str = "http://investigator:8100"

    # How many recent rows to load on each page render.
    alerts_limit: int = 200
    investigations_limit: int = 100

    @model_validator(mode="after")
    def _build_dsn_from_parts(self) -> "Settings":
        if self.db_user and self.db_host:
            self.db_dsn = (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
