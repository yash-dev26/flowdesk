import re
import zlib

import numpy as np
from langchain_core.embeddings import Embeddings

from app.config import Settings

_STOP = {"the", "a", "an", "is", "are", "to", "of", "and", "or", "my", "i", "me", "it",
         "in", "on", "for", "you", "your", "can", "do", "how", "what", "with", "this", "that"}


class HashingEmbeddings(Embeddings):
    """Offline bag-of-words embeddings (feature hashing + L2 norm).

    Not semantic, but deterministic and dependency-free, so tests and
    `EMBEDDING_PROVIDER=hashing` need no model download.
    """

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = np.zeros(self.dim)
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            if tok in _STOP:
                continue
            tok = re.sub(r"(ing|ed|es|s)$", "", tok) if len(tok) > 4 else tok
            v[zlib.crc32(tok.encode()) % self.dim] += 1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FastEmbedEmbeddings(Embeddings):
    """Local ONNX embeddings via fastembed (no API key; model downloads on first use)."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding  # imported lazily: optional at test time

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embeddings(settings: Settings) -> Embeddings:
    name = settings.embedding_provider.lower()
    if name == "hashing":
        return HashingEmbeddings()
    if name == "fastembed":
        return FastEmbedEmbeddings(settings.embedding_model)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider!r}")
