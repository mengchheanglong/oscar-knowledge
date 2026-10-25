"""Independent knowledge schema; never touches OSCAR tables."""

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    # Explicit immutable DDL, independent of the application's evolving ORM models.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
    CREATE TABLE collections (
      id uuid PRIMARY KEY, slug varchar(100) NOT NULL UNIQUE, title varchar(300) NOT NULL,
      description text NOT NULL DEFAULT '', visibility varchar(30) NOT NULL DEFAULT 'CURATED_SHARED',
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK (visibility = 'CURATED_SHARED')
    );
    CREATE TABLE documents (
      id uuid PRIMARY KEY, collection_id uuid NOT NULL REFERENCES collections(id),
      canonical_key varchar(500) NOT NULL, source_url text, local_path text NOT NULL,
      title varchar(500) NOT NULL, institution varchar(300), course_code varchar(100),
      course_title varchar(300), subject varchar(100), content_type varchar(50) NOT NULL,
      language varchar(20) NOT NULL DEFAULT 'en', author varchar(300), publication_year integer,
      license_type varchar(100) NOT NULL DEFAULT 'USER_AUTHORIZED', license_url text,
      usage_notes text NOT NULL DEFAULT '', approved boolean NOT NULL DEFAULT false,
      content_sha256 varchar(64), active_revision integer NOT NULL DEFAULT 0,
      parser_version varchar(100), embedding_identity varchar(300),
      status varchar(30) NOT NULL DEFAULT 'DISCOVERED', error_code varchar(100),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(collection_id, canonical_key)
    );
    CREATE INDEX ix_documents_collection_id ON documents(collection_id);
    CREATE INDEX ix_documents_course_code ON documents(course_code);
    CREATE INDEX ix_documents_subject ON documents(subject);
    CREATE INDEX ix_documents_publication_year ON documents(publication_year);
    CREATE INDEX ix_documents_content_sha256 ON documents(content_sha256);
    CREATE INDEX ix_documents_status ON documents(status);
    CREATE TABLE chunks (
      id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id),
      collection_id uuid NOT NULL REFERENCES collections(id), revision integer NOT NULL,
      ordinal integer NOT NULL, text text NOT NULL, char_count integer NOT NULL,
      token_estimate integer NOT NULL, heading_path text, page_start integer, page_end integer,
      start_ms integer, end_ms integer, source_metadata jsonb NOT NULL DEFAULT '{}',
      embedding vector(1536), embedding_identity varchar(300),
      search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(document_id, revision, ordinal)
    );
    CREATE INDEX ix_chunks_active ON chunks(collection_id, document_id, revision);
    CREATE INDEX ix_chunks_fts ON chunks USING gin(search_vector);
    CREATE TABLE ingestion_jobs (
      id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id),
      status varchar(30) NOT NULL DEFAULT 'QUEUED', stage varchar(30) NOT NULL DEFAULT 'queued',
      attempts integer NOT NULL DEFAULT 0, progress integer NOT NULL DEFAULT 0,
      error_code varchar(100), checkpoint jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz
    );
    CREATE INDEX ix_ingestion_jobs_status ON ingestion_jobs(status);
    CREATE INDEX ix_ingestion_jobs_document_id ON ingestion_jobs(document_id);
    INSERT INTO collections(id, slug, title) VALUES
      ('3b2806fa-3540-4fc8-b3c4-9720f5aa32da', 'mba-business', 'MBA Business');
    """)


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup instead")
