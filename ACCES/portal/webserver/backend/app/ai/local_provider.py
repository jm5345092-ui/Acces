from __future__ import annotations

from app.ai.provider import AIProvider, ModificationPlan


class LocalProvider(AIProvider):
    """Stub for a locally-hosted model (e.g. an Ollama endpoint). No local
    model is available in this environment to validate a prompt/parsing
    contract against, so this intentionally raises rather than pretending
    to work."""

    def plan(self, project_context: dict, instruction: str) -> ModificationPlan:
        raise NotImplementedError(
            "LocalProvider is a placeholder. Point it at your local inference "
            "server and reuse ClaudeProvider's JSON-plan contract/prompt."
        )
