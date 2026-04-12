from functools import lru_cache

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

    # Postgres connection (sync). In AWS, the DSN is constructed at startup from
    # Secrets Manager; locally it comes from docker-compose env.
    db_dsn: str = "postgresql+psycopg://pgscp:pgscp@postgres:5432/pgscp"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
