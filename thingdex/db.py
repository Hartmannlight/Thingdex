import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _default_database_url() -> str:
    return "postgresql+psycopg://thingdex:thingdex@127.0.0.1:5432/thingdex"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
