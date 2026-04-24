from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PGSCP_", env_file=None, extra="ignore")

    env: str = "local"
    service_name: str = "pgscp-investigator"
    log_level: str = "INFO"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""

    s3_raw_bucket: str = "pgscp-raw-events-local"
    investigations_queue_url: str = ""

    # Postgres -- single DSN for local dev, or individual parts for AWS (where
    # the RDS-managed secret delivers user+password separately from the host).
    db_dsn: str = "postgresql+psycopg://pgscp:pgscp@postgres:5432/pgscp"
    db_user: str = ""
    db_password: str = ""
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "pgscp"

    slack_webhook_url: str = ""
    hmac_signing_key: str = "local-dev-only-not-a-real-secret"

    sqs_wait_time_seconds: int = 20
    sqs_visibility_timeout: int = 180
    sqs_max_messages: int = 1

    llm_backend: str = "scripted"  # scripted | bedrock | openai
    llm_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.2
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"

    cloudwatch_api_log_group: str = "/pgscp/dev/api"
    cloudwatch_worker_log_group: str = "/pgscp/dev/worker"
    ecs_cluster: str = "pgscp-dev"

    graph_verify_max_loops: int = 2
    graph_confidence_threshold: float = 0.7

    feedback_port: int = 8100

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
