from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PGSCP_", env_file=None, extra="ignore")

    env: str = "local"
    service_name: str = "pgscp-worker"
    log_level: str = "INFO"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""

    s3_raw_bucket: str = "pgscp-raw-events-local"
    sqs_queue_url: str = ""
    investigations_queue_url: str = ""

    # Postgres — either a full DSN (local dev) or individual parts (AWS, where
    # the RDS-managed secret delivers user+password separately from the host).
    # When `db_user` and `db_host` are both set, they take precedence and
    # `db_dsn` is rebuilt from the parts.
    db_dsn: str = "postgresql+psycopg://pgscp:pgscp@postgres:5432/pgscp"
    db_user: str = ""
    db_password: str = ""
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "pgscp"

    # Rule thresholds — deliberately tunable via env for incident simulations.
    latency_breach_ms: int = 1500
    cost_anomaly_threshold_usd: float = 0.50
    accuracy_drift_floor: float = 0.80
    stuck_model_window: int = 20
    missing_heartbeat_minutes: int = 10

    # Partner integrations (pointed at mock-partner in local).
    slack_webhook_url: str = ""
    pagerduty_url: str = ""
    hmac_signing_key: str = "local-dev-only-not-a-real-secret"

    # SQS long-polling + visibility
    sqs_wait_time_seconds: int = 20
    sqs_visibility_timeout: int = 60
    sqs_max_messages: int = 10

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
