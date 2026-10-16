"""OllamaClient tests against a mock HTTP transport (no Ollama server needed)."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.services.llm import LLMError, LLMUnavailableError
from app.services.ollama import OllamaClient

Handler = Callable[[httpx.Request], httpx.Response]


def client_with(handler: Handler) -> OllamaClient:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaClient(http_client, "http://ollama.test/", "qwen2.5:7b")


def test_sends_chat_request_and_returns_content() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Hi [1]."}})

    assert client_with(handler).complete("system rules", "user prompt") == "Hi [1]."

    (request,) = seen
    assert str(request.url) == "http://ollama.test/api/chat"
    body = json.loads(request.content)
    assert body == {
        "model": "qwen2.5:7b",
        "messages": [
            {"role": "system", "content": "system rules"},
            {"role": "user", "content": "user prompt"},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }


def test_server_not_running_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LLMUnavailableError, match="ollama serve"):
        client_with(handler).complete("s", "u")


def test_missing_model_is_unavailable_with_pull_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(LLMUnavailableError, match="ollama pull qwen2.5:7b"):
        client_with(handler).complete("s", "u")


def test_timeout_is_an_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMError, match="too long"):
        client_with(handler).complete("s", "u")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="internal error"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"unexpected": "shape"}),
        httpx.Response(200, json={"message": {"content": None}}),
    ],
)
def test_bad_responses_are_llm_errors(response: httpx.Response) -> None:
    with pytest.raises(LLMError):
        client_with(lambda _request: response).complete("s", "u")
