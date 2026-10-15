"""AI provider abstraction (spec section 13).

The AI never touches files directly. `plan()` returns a `ModificationPlan`
— an ordered list of the exact same structured operations the manual
Modification Engine understands (`create_smali_class`,
`insert_smali_instruction`, etc.). The frontend renders the plan, the user
reviews a diff per step, and only an explicit "Apply" call runs them
through `smali_service`/`resource_service`/`manifest_service` — identical
to a hand-authored modification.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PlanStep:
    operation: str
    params: dict
    rationale: str = ""


@dataclass
class ModificationPlan:
    steps: list[PlanStep] = field(default_factory=list)
    summary: str = ""


class AIProvider(ABC):
    @abstractmethod
    def plan(self, project_context: dict, instruction: str) -> ModificationPlan:
        """`project_context` should include package name, discovered main
        activity, available smali modules, and a short project tree — never
        the full decompiled source (keeps prompts small and avoids leaking
        unrelated decompiled code into a third-party API call unnecessarily)."""


def get_provider(name: str) -> AIProvider:
    if name == "claude":
        from app.ai.claude_provider import ClaudeProvider

        return ClaudeProvider()
    if name == "openai":
        from app.ai.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "local":
        from app.ai.local_provider import LocalProvider

        return LocalProvider()
    raise ValueError(f"Unknown AI provider: {name}")
