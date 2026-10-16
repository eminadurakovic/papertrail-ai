"""Text embeddings with bge-small-en-v1.5 (ONNX, CLS pooling, unit-length vectors)."""

import logging
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt
import onnxruntime
from tokenizers import Tokenizer

from app.models.passage import EMBEDDING_DIMENSION

logger = logging.getLogger(__name__)

# float32 array: shape (number of texts, dimension), or (dimension,) for a single query.
Vectors = npt.NDArray[np.float32]

MODEL_FILE = "model_optimized.onnx"
TOKENIZER_FILE = "tokenizer.json"
MAX_TOKENS = 512  # the model's input limit; longer texts are truncated
# bge recommends this prefix for short search queries (not for the passages themselves).
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class EmbeddingError(Exception):
    """Embedding failed. Messages are safe to show to users."""


class EmbeddingModelUnavailableError(EmbeddingError):
    """The model files are missing or could not be loaded."""


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> Vectors: ...

    def embed_query(self, text: str) -> Vectors: ...


class OnnxEmbedder:
    model_name = "BAAI/bge-small-en-v1.5"
    dimension = EMBEDDING_DIMENSION

    def __init__(self, model_dir: Path, batch_size: int = 32) -> None:
        model_path, tokenizer_path = model_dir / MODEL_FILE, model_dir / TOKENIZER_FILE
        if not model_path.is_file() or not tokenizer_path.is_file():
            raise EmbeddingModelUnavailableError(
                f"Embedding model files not found in {model_dir}. See the README section "
                "'Embedding model' for how to set them up."
            )
        try:
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
            self._session = onnxruntime.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # corrupt files raise various library-specific errors
            raise EmbeddingModelUnavailableError(
                "The embedding model could not be loaded."
            ) from exc

        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer.enable_padding()  # pad each batch to its longest text
        self._batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> Vectors:
        batches = [
            self._embed_batch(texts[start : start + self._batch_size])
            for start in range(0, len(texts), self._batch_size)
        ]
        if not batches:
            return np.empty((0, self.dimension), dtype=np.float32)
        return np.vstack(batches)

    def embed_query(self, text: str) -> Vectors:
        return np.asarray(self._embed_batch([QUERY_INSTRUCTION + text])[0], dtype=np.float32)

    def _embed_batch(self, texts: list[str]) -> Vectors:
        encodings = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        try:
            (token_vectors,) = self._session.run(
                ["last_hidden_state"],
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": np.zeros_like(input_ids),
                },
            )
        except Exception as exc:  # onnxruntime raises its own error types
            logger.exception("Embedding model inference failed")
            raise EmbeddingError("The embedding model failed to process the text.") from exc

        cls_vectors = np.asarray(token_vectors[:, 0, :], dtype=np.float32)
        return normalize(cls_vectors)


def normalize(vectors: Vectors) -> Vectors:
    """Scale each row to length 1 (rows of all zeros are left unchanged)."""
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return np.asarray(vectors / np.where(norms == 0, 1, norms), dtype=np.float32)
