import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


def test_0002_preserves_an_actual_0001_vector(db, monkeypatch):
    """Exercise upgrade on a fresh generated schema in the disposable test DB."""
    url = db.bind.url
    assert url.database.endswith("_test")
    schema = "qwen_migration_" + uuid.uuid4().hex + "_test"
    with db.bind.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        # Prevent lookup from finding the public schema's Alembic version table.
        conn.execute(
            text(f'CREATE TABLE "{schema}".alembic_version (version_num varchar(32) PRIMARY KEY)')
        )
    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema},public"})
    engine = create_engine(scoped_url)
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "0001")
        document, chunk = uuid.uuid4(), uuid.uuid4()
        vector = "[1," + ",".join(["0"] * 1535) + "]"
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO documents (id, collection_id, canonical_key, local_path, title, content_type, approved, active_revision)
                VALUES (:id, '3b2806fa-3540-4fc8-b3c4-9720f5aa32da', 'migration-fixture', 'unneeded.md', 'Synthetic legacy fixture', '.md', true, 1)"""),
                {"id": document},
            )
            conn.execute(
                text("""INSERT INTO chunks (id, document_id, collection_id, revision, ordinal, text, char_count, token_estimate, embedding, embedding_identity)
                VALUES (:id, :doc, '3b2806fa-3540-4fc8-b3c4-9720f5aa32da', 1, 0, 'Legacy pricing evidence', 23, 6, CAST(:vector AS vector), 'legacy-identity')"""),
                {"id": chunk, "doc": document, "vector": vector},
            )
            before = conn.execute(
                text(
                    "SELECT id, document_id, revision, md5(embedding::text), embedding_identity FROM chunks"
                )
            ).one()
        command.upgrade(Config("alembic.ini"), "head")
        with engine.connect() as conn:
            after = conn.execute(
                text(
                    "SELECT id, document_id, revision, md5(embedding::text), embedding_identity FROM chunks"
                )
            ).one()
            assert before == after
            assert conn.scalar(text("SELECT vector_dims(embedding) FROM chunks")) == 1536
            assert conn.scalar(text("SELECT count(*) FROM chunk_embeddings")) == 0
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0006"
            assert conn.scalar(text("SELECT count(*) FROM library_books")) == 0
    finally:
        engine.dispose()
        get_settings.cache_clear()
        # Only this generated test schema is removed; no populated application schema.
        assert schema.startswith("qwen_migration_") and schema.endswith("_test")
        with db.bind.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
