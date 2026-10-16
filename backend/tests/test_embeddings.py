"""Embedding tests. The `model` tests load the real model: pytest -m model"""

from pathlib import Path

import numpy as np
import pytest

from app.core.config import get_settings
from app.services.embeddings import (
    EmbeddingModelUnavailableError,
    OnnxEmbedder,
    normalize,
)
from tests.fake_embedder import FakeEmbedder


def test_normalize_scales_rows_to_unit_length() -> None:
    vectors = np.array([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32)

    assert np.allclose(normalize(vectors), [[0.6, 0.8], [0.0, 1.0]])


def test_normalize_leaves_zero_vectors_alone() -> None:
    assert np.array_equal(normalize(np.zeros((1, 3), dtype=np.float32)), np.zeros((1, 3)))


def test_missing_model_files_give_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(EmbeddingModelUnavailableError, match="README"):
        OnnxEmbedder(tmp_path)


def test_corrupt_model_file_gives_a_clear_error(tmp_path: Path) -> None:
    (tmp_path / "model_optimized.onnx").write_bytes(b"not a model")
    (tmp_path / "tokenizer.json").write_text("{}")

    with pytest.raises(EmbeddingModelUnavailableError, match="could not be loaded"):
        OnnxEmbedder(tmp_path)


def test_fake_embedder_is_deterministic_and_normalized() -> None:
    first, second = FakeEmbedder(), FakeEmbedder()
    texts = ["attention is all you need", "graph neural networks"]

    a, b = first.embed_documents(texts), second.embed_documents(texts)

    assert a.shape == (2, 384)
    assert np.array_equal(a, b)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)


# --- real model (opt-in) ----------------------------------------------------------


@pytest.fixture(scope="module")
def real_embedder() -> OnnxEmbedder:
    return OnnxEmbedder(get_settings().embedding_model_dir)


@pytest.mark.model
def test_real_model_returns_normalized_384d_vectors(real_embedder: OnnxEmbedder) -> None:
    vectors = real_embedder.embed_documents(["first passage", "a second, longer passage"])

    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


@pytest.mark.model
def test_real_model_batches_give_same_result_as_single_texts(real_embedder: OnnxEmbedder) -> None:
    """Padding inside a batch must not change a text's embedding."""
    texts = ["short", "a much longer text that forces the short one to be padded in the batch"]

    batched = real_embedder.embed_documents(texts)
    one_by_one = np.vstack([real_embedder.embed_documents([t]) for t in texts])

    assert np.allclose(batched, one_by_one, atol=1e-4)


@pytest.mark.model
def test_real_model_places_related_texts_closer(real_embedder: OnnxEmbedder) -> None:
    query = real_embedder.embed_query("How does self-attention work?")
    passages = real_embedder.embed_documents(
        [
            "Self-attention relates different positions of a sequence to compute a representation.",
            "The recipe calls for two cups of flour and a pinch of salt.",
        ]
    )

    related, unrelated = passages @ query  # dot product = cosine similarity (unit vectors)
    assert related > unrelated + 0.2


@pytest.mark.model
def test_real_model_handles_empty_input_and_long_text(real_embedder: OnnxEmbedder) -> None:
    assert real_embedder.embed_documents([]).shape == (0, 384)
    long_text = "word " * 2000  # far beyond 512 tokens -> truncated, not an error
    assert real_embedder.embed_documents([long_text]).shape == (1, 384)
