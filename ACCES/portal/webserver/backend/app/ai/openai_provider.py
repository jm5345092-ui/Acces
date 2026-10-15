from __future__ import annotations

from app.ai.provider import AIProvider, ModificationPlan


class OpenAIProvider(AIProvider):
    """Stub — no OpenAI API key/SDK available to validate against in this
    environment. Wire up similarly to ClaudeProvider (same JSON-plan
    contract) once you have a key to test with."""

    def plan(self, project_context: dict, instruction: str) -> ModificationPlan:
        raise NotImplementedError(
            "OpenAIProvider is a placeholder. Implement using the openai SDK "
            "and OPENAI_API_KEY, following ClaudeProvider's JSON-plan contract."
        )
