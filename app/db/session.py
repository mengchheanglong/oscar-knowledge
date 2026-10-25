from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def engine():
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"},
    )


def session() -> Session:
    return sessionmaker(engine(), expire_on_commit=False)()
