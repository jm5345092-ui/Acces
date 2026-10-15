"""Plan §14 test H: the AssistantProvider must never register tools/
function-calling with the model, and its output type must have no
action/command/tool/execute field."""
from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

from app.assistant.claude_assistant_provider import ClaudeAssistantProvider
from app.assistant.provider import AssistantAnswer, AssistantTurn


class _StubMessages:
    def __init__(self):
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        payload = {
            "mode": "teaching",
            "message": "explicación educativa de prueba",
            "observation": "",
            "analysis": "",
            "possible_problem": "",
            "evidence": "",
            "suggestion": "",
            "confidence": "",
        }
        text_block = SimpleNamespace(type="text", text=json.dumps(payload))
        return SimpleNamespace(content=[text_block])


def _provider_with_stub_client() -> tuple[ClaudeAssistantProvider, _StubMessages]:
    provider = object.__new__(ClaudeAssistantProvider)
    stub_messages = _StubMessages()
    provider._client = SimpleNamespace(messages=stub_messages)
    return provider, stub_messages


def test_assistant_answer_has_no_action_fields():
    field_names = {f.name for f in dataclasses.fields(AssistantAnswer)}
    assert field_names == {
        "message",
        "mode",
        "observation",
        "analysis",
        "possible_problem",
        "evidence",
        "suggestion",
        "confidence",
    }
    for forbidden in ("action", "command", "tool", "execute", "tools"):
        assert forbidden not in field_names


def test_claude_assistant_provider_never_passes_tools_kwarg():
    provider, stub = _provider_with_stub_client()
    answer = provider.answer(
        project_context={"package": "com.example.app"},
        history=[AssistantTurn(role="user", content="hola")],
        question="¿Qué es un intent-filter?",
    )

    assert stub.last_kwargs is not None
    assert "tools" not in stub.last_kwargs
    assert "tool_choice" not in stub.last_kwargs
    assert isinstance(answer, AssistantAnswer)
    assert answer.mode == "teaching"
