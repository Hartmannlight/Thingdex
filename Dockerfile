FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml poetry.lock README.md /app/
COPY alembic /app/alembic
COPY alembic.ini /app/
COPY thingdex /app/thingdex

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "thingdex.main:app", "--host", "0.0.0.0", "--port", "8000"]
