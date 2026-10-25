from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ChunkEmbedding
from app.embeddings.base import validate_vectors, EmbeddingError


def store_vectors(db, chunks, vectors, embedder, settings):
    validate_vectors(vectors, len(chunks), embedder.dimensions)
    if not chunks:
        return
    db.execute(text("SELECT pg_advisory_xact_lock(7643921)"))
    count = db.scalar(select(func.count()).select_from(ChunkEmbedding)) or 0
    if count + len(chunks) > settings.max_embedding_rows:
        raise EmbeddingError("EMBEDDING_STORAGE_QUOTA")
    rows = [
        {
            "chunk_id": chunk.id,
            "identity": embedder.identity,
            "dimensions": embedder.dimensions,
            "embedding_1024": vector if embedder.dimensions == 1024 else None,
            "embedding_1536": vector if embedder.dimensions == 1536 else None,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    db.execute(
        insert(ChunkEmbedding)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["chunk_id", "identity"])
    )
