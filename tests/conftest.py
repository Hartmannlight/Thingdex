import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError

DEFAULT_DATABASE_URL = "postgresql+psycopg://thingdex:thingdex@localhost:5432/thingdex"


def _base_database_url() -> str:
    return (
        os.environ.get("THINGDEX_TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )


def _clear_thingdex_modules() -> None:
    for name in list(sys.modules):
        if name == "thingdex" or name.startswith("thingdex."):
            sys.modules.pop(name)


@contextmanager
def _client_with_label_enabled(label_enabled: str):
    base_url = make_url(_base_database_url())
    base_engine = create_engine(base_url, pool_pre_ping=True)
    try:
        with base_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Database not available for integration tests.")

    schema_name = f"test_{uuid.uuid4().hex}"
    with base_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    original_database_url = os.environ.get("DATABASE_URL")
    query = dict(base_url.query)
    query["options"] = f"-csearch_path={schema_name}"
    os.environ["DATABASE_URL"] = base_url.set(query=query).render_as_string(hide_password=False)
    os.environ["LABEL_PRINTING_ENABLED"] = label_enabled

    _clear_thingdex_modules()
    from thingdex import db, models
    from thingdex.main import app

    models.Base.metadata.create_all(bind=db.engine)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        with base_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


@pytest.fixture()
def client():
    with _client_with_label_enabled("false") as test_client:
        yield test_client


@pytest.fixture()
def label_client():
    with _client_with_label_enabled("true") as test_client:
        yield test_client
