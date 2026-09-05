FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/app/.venv/bin:$PATH

FROM base AS dependencies

ARG POETRY_VERSION=2.4.1
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

COPY pyproject.toml poetry.lock README.md /app/
RUN python -m pip install --no-cache-dir "poetry==${POETRY_VERSION}" \
    && poetry check --lock \
    && poetry sync --only main --no-root \
    && /app/.venv/bin/python -m pip uninstall -y pip setuptools wheel jaraco.context

FROM base AS runtime

RUN python -m pip uninstall -y pip setuptools wheel jaraco.context \
    && groupadd --system thingdex \
    && useradd --system --gid thingdex --home-dir /app thingdex

COPY --from=dependencies /app/.venv /app/.venv
COPY alembic /app/alembic
COPY alembic.ini /app/
COPY thingdex /app/thingdex
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh

RUN chmod 0555 /app/scripts/docker-entrypoint.sh \
    && chown -R thingdex:thingdex /app

USER thingdex

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import http.client; connection=http.client.HTTPConnection('127.0.0.1', 8000, timeout=3); connection.request('GET', '/health/ready'); assert connection.getresponse().status == 200"]

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "thingdex.main:app", "--host", "0.0.0.0", "--port", "8000"]
