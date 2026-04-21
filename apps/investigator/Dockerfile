FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY investigator ./investigator
COPY eval ./eval

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin pgscp && \
    chown -R pgscp:pgscp /app
USER pgscp

CMD ["python", "-m", "investigator.main"]
