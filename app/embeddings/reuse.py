"""Reuse vectors only for byte-identical input text and the exact embedding identity.

This is an internal computation cache. Each new chunk retains independent source
provenance, owner/permission gates and vector rows; no access grant is transferred.
"""

import hashlib

from sqlalchemy import func, select

from app.db.models import Chunk, ChunkEmbedding
from app.embeddings.base import validate_vectors


def embed_with_reuse(db, texts, embedder):
    unique = list(dict.fromkeys(texts))
    hashes = [hashlib.md5(t.encode("utf-8"), usedforsecurity=False).hexdigest() for t in unique]
    vector_column = (
        ChunkEmbedding.embedding_1024
        if embedder.dimensions == 1024
        else ChunkEmbedding.embedding_1536
    )
    rows = db.execute(
        select(Chunk.text, vector_column)
        .join(ChunkEmbedding, Chunk.id == ChunkEmbedding.chunk_id)
        .where(
            func.md5(Chunk.text).in_(hashes),
            ChunkEmbedding.identity == embedder.identity,
            ChunkEmbedding.dimensions == embedder.dimensions,
            vector_column.is_not(None),
        )
        .distinct(func.md5(Chunk.text))
        .order_by(func.md5(Chunk.text), Chunk.id)
    )
    wanted = set(unique)
    known = {t: [float(value) for value in v] for t, v in rows if t in wanted}
    missing = [t for t in unique if t not in known]
    embedder.batch_results = []
    if missing:
        vectors = embedder.embed_documents(missing)
        validate_vectors(vectors, len(missing), embedder.dimensions)
        known.update(zip(missing, vectors, strict=True))
    reused = len(texts) - len(missing)
    if reused:
        embedder.batch_results.append({"status": "REUSED_EXACT_TEXT", "count": reused})
    return validate_vectors([known[t] for t in texts], len(texts), embedder.dimensions)
