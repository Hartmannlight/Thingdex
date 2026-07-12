FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system thingdex && useradd --system --gid thingdex --home-dir /app thingdex \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml poetry.lock README.md /app/
COPY alembic /app/alembic
COPY alembic.ini /app/
COPY thingdex /app/thingdex
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod 0555 /app/scripts/docker-entrypoint.sh \
    && chown -R thingdex:thingdex /app

USER thingdex

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "thingdex.main:app", "--host", "0.0.0.0", "--port", "8000"]
