import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.fixture()
def db():
    url = os.getenv("KNOWLEDGE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("KNOWLEDGE_TEST_DATABASE_URL not configured")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Refusing integration tests outside a *_test database")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE ingestion_jobs, chunks, documents"))
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()
