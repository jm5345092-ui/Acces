"""AssistantProvider — TEXT/STRUCTURED-OUTPUT ONLY (plan §7/§8).

`AssistantAnswer` has no field for an action/command/tool/execute — it can
only ever carry prose and the OBSERVACIÓN/ANÁLISIS/POSIBLE PROBLEMA/
EVIDENCIA/SUGERENCIA/CONFIANZA fields the user asked for. No implementation
of this interface is allowed to register tools/function-calling with the
underlying model — `tests/test_assistant_provider_no_tools.py` asserts this
for the Claude implementation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AssistantAnswer:
    message: str
    mode: str = "general"  # "finding" | "teaching" | "general"
    observation: str = ""
    analysis: str = ""
    possible_problem: str = ""
    evidence: str = ""
    suggestion: str = ""
    confidence: str = ""


@dataclass
class AssistantTurn:
    role: str  # "user" | "assistant"
    content: str


class AssistantProvider(ABC):
    @abstractmethod
    def answer(
        self,
        *,
        project_context: dict,
        history: list[AssistantTurn],
        question: str,
    ) -> AssistantAnswer:
        """`project_context` is the explicit whitelist built by
        `AssistantService` (manifest summary, counts, findings, recent
        events) — never `.env` contents, keystore passwords, or raw file
        dumps. Implementations must not expose tool/function-calling to the
        underlying model."""


def get_assistant_provider(name: str) -> AssistantProvider:
    if name == "claude":
        from app.assistant.claude_assistant_provider import ClaudeAssistantProvider

        return ClaudeAssistantProvider()
    raise ValueError(f"Unknown assistant provider: {name}")
