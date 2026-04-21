import os

os.environ.setdefault("PGSCP_ENV", "test")
os.environ.setdefault("PGSCP_LLM_BACKEND", "scripted")
os.environ.setdefault("PGSCP_DB_DSN", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PGSCP_AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("PGSCP_LOG_LEVEL", "WARNING")

from investigator.llm import reset_backend  # noqa: E402
from investigator.settings import get_settings  # noqa: E402

get_settings.cache_clear()  # type: ignore[attr-defined]
reset_backend()
