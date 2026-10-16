"""A deterministic stand-in for the embedding model, used by almost all tests.

Each word is hashed to one of the 384 dimensions ("bag of words"), then the vector is
normalized. Texts sharing words get similar vectors, which is enough to test storage
and retrieval logic without loading a real model.
"""

import hashlib

import numpy as np

from app.models.passage import EMBEDDING_DIMENSION
from app.services.embeddings import EmbeddingError, Vectors, normalize


class FakeEmbedder:
    model_name = "fake-bag-of-words"
    dimension = EMBEDDING_DIMENSION

    def __init__(self) -> None:
        self.calls = 0
        self.output_dimension = EMBEDDING_DIMENSION  # change to simulate a broken model
        self.fail_with: EmbeddingError | None = None
        self.salt = ""  # change to make every vector different (simulates a new model)

    def vector(self, text: str) -> Vectors:
        vector = np.zeros(self.output_dimension, dtype=np.float32)
        for word in text.lower().split():
            digest = hashlib.sha256((self.salt + word).encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.output_dimension] += 1.0
        if not vector.any():
            vector[0] = 1.0
        return normalize(vector)

    def embed_documents(self, texts: list[str]) -> Vectors:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        if not texts:
            return np.empty((0, self.output_dimension), dtype=np.float32)
        return np.vstack([self.vector(text) for text in texts])

    def embed_query(self, text: str) -> Vectors:
        return self.vector(text)
