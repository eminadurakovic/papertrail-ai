"""A scripted stand-in for a language model. Records every prompt it receives."""

from dataclasses import dataclass, field

from app.services.llm import LLMError


@dataclass
class FakeLLM:
    reply: str = "The model uses attention [1]."
    error: LLMError | None = None
    model_name: str = "fake-llm"
    prompts: list[tuple[str, str]] = field(default_factory=list)  # (system, user)

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        if self.error is not None:
            raise self.error
        return self.reply

    @property
    def last_user_prompt(self) -> str:
        return self.prompts[-1][1]
