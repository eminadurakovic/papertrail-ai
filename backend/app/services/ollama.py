"""LLMClient implementation for a local Ollama server (https://ollama.com).

Ollama runs open-weight models on this machine and exposes an HTTP API on
localhost:11434. We call POST /api/chat once per question, without streaming.
"""

import logging

import httpx

from app.services.llm import LLMError, LLMUnavailableError

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, http_client: httpx.Client, base_url: str, model: str) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self.model_name = model

    def complete(self, system: str, user: str) -> str:
        try:
            response = self._http.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    # temperature 0 = most deterministic output, best for grounded answers
                    "options": {"temperature": 0},
                },
            )
        except httpx.TimeoutException as exc:
            raise LLMError("The language model took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(
                f"Could not reach Ollama at {self._base_url}. Is it running (`ollama serve`)?"
            ) from exc

        if response.status_code == 404:
            raise LLMUnavailableError(
                f"Model '{self.model_name}' is not installed. Run `ollama pull {self.model_name}`."
            )
        if response.status_code != 200:
            logger.error("Ollama returned HTTP %s: %s", response.status_code, response.text[:500])
            raise LLMError(f"The language model failed (HTTP {response.status_code}).")

        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("The language model returned an unexpected response.") from exc
        if not isinstance(content, str):
            raise LLMError("The language model returned an unexpected response.")
        return content
