from app.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.ollama_provider import OllamaEmbedding
from app.embeddings.openai_provider import OpenAICompatible


def provider(settings: Settings) -> EmbeddingProvider | None:
    if settings.embedding_provider == "ollama":
        return OllamaEmbedding(settings)
    if settings.embedding_provider == "openai":
        return OpenAICompatible(settings)
    return None
