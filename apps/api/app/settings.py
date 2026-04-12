from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PGSCP_", env_file=None, extra="ignore")

    env: str = "local"
    service_name: str = "pgscp-api"
    log_level: str = "INFO"

    aws_region: str = "us-east-1"
    # LocalStack override: set to e.g. http://localstack:4566 in docker-compose.
    # Empty string means "use real AWS".
    aws_endpoint_url: str = ""

    s3_raw_bucket: str = "pgscp-raw-events-local"
    s3_kms_key_id: str = ""  # empty = use SSE-S3 (fine for local)

    sqs_queue_url: str = ""

    max_payload_bytes: int = 32 * 1024

    otel_exporter_otlp_endpoint: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
