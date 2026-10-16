"""Minimal LLM interface used by the RAG service."""

from typing import Protocol


class LLMError(Exception):
    """The language model call failed. Messages are safe to show to users."""


class LLMNotConfiguredError(LLMError):
    """No language model is configured, so answers cannot be generated."""


class LLMUnavailableError(LLMError):
    """The model server can't be reached or the model isn't installed."""


class LLMClient(Protocol):
    @property
    def model_name(self) -> str: ...

    def complete(self, system: str, user: str) -> str:
        """Return the model's text reply. Raise LLMError on failure."""
        ...
