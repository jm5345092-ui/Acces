from __future__ import annotations

import json

from app.ai.provider import AIProvider, ModificationPlan, PlanStep
from app.core.config import get_settings

_SYSTEM_PROMPT = """You are a planning assistant for an APK reverse-engineering lab tool.
Given a project context (package name, discovered main activity, available Smali
modules) and a user instruction, output ONLY a JSON object of the form:
{"summary": "...", "steps": [{"operation": "create_smali_package", "params": {...}, "rationale": "..."}]}

Valid operations and their params:
- create_smali_package: {"package": "com.example.foo"}
- create_smali_class: {"package": "com.example.foo", "class_name": "Logger", "module": "smali_classes3" (optional)}
- insert_smali_instruction: {"target_class": "com/example/foo/MainActivity", "target_method": "onCreate(Landroid/os/Bundle;)V", "instruction": "invoke-static {}, Lcom/example/foo/Logger;->ejecutar()V", "position": "start"|"end"}
- replace_smali_block: {"target_class": "...", "search_block": "...", "replacement_block": "..."}
- modify_manifest: {"xpath": "...", "attribute": "...", "value": "..."}

Never invent classes/methods that don't exist in the provided context. If information is
missing, ask for it via a step with operation "clarify" instead of guessing.
Output JSON only, no prose, no markdown fences."""


class ClaudeProvider(AIProvider):
    """Real implementation using the Anthropic SDK. Requires
    ANTHROPIC_API_KEY — if unset, `plan()` raises immediately rather than
    silently no-op'ing, since I have no key to test this against in this
    environment."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            self._client = None
        else:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def plan(self, project_context: dict, instruction: str) -> ModificationPlan:
        if self._client is None:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured; the AI assistant is disabled. "
                "Set it in your .env to enable AI-planned modifications."
            )

        message = self._client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Project context:\n{json.dumps(project_context, indent=2)}\n\n"
                        f"Instruction: {instruction}"
                    ),
                }
            ],
        )
        raw_text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        data = json.loads(raw_text)
        steps = [
            PlanStep(
                operation=step["operation"],
                params=step.get("params", {}),
                rationale=step.get("rationale", ""),
            )
            for step in data.get("steps", [])
        ]
        return ModificationPlan(steps=steps, summary=data.get("summary", ""))
