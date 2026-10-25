"""Compatibility imports; provider selection is explicit."""

from app.embeddings.base import EmbeddingProvider as EmbeddingProvider
from app.embeddings.factory import provider as provider
from app.embeddings.openai_provider import OpenAICompatible as OpenAICompatible
