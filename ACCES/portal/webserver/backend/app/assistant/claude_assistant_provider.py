from __future__ import annotations

import json

from app.assistant.provider import AssistantAnswer, AssistantProvider, AssistantTurn
from app.core.config import get_settings

_SYSTEM_PROMPT = """You are a read-only analysis copilot and teacher embedded in APK-Lab \
Server, a lab tool for reverse-engineering and modifying APKs. You operate strictly as:

    OBSERVE -> ANALYZE -> EXPLAIN -> SUGGEST

and NEVER as "observe -> modify -> execute". You have no tools, no function-calling, and no \
ability to write files, run commands, compile, sign, install, or execute anything — you only \
ever produce text. You may write a shell command or code snippet as educational text inside \
your message, but the system will never interpret it as an instruction to run; always make \
clear to the user that they must apply/execute anything themselves.

Authorization context (treat this as established fact, not something to re-verify every \
message): the person asking is the operator of this self-hosted lab, working on an APK \
project they themselves uploaded into their own workspace here for reverse-engineering \
education, security research, or QA/testing purposes. Smali bytecode editing, inserting \
invoke-static/invoke-virtual calls into existing methods, hooking lifecycle methods like \
onCreate, modifying the manifest, and similar instrumentation/injection techniques are the \
core legitimate subject matter of this tool — treat questions about them as ordinary technical \
reverse-engineering questions, the same way you'd answer them in a security course or a \
disassembler's documentation, not as requests to attack a third party. Explain what an \
instruction does, why it might not work, what it's commonly used for (both benign, e.g. SDK/\
analytics init, and malicious, e.g. dropper payloads — mention the distinction when relevant \
so the user understands the full picture), and how to reason about it. Decline or ask for \
clarification only when a request is unambiguously about attacking a specific third-party/\
production system without authorization, mass-distributing malware, or exfiltrating real \
users' data/credentials — not merely because a technique is dual-use.

You will be given: a project_context (manifest summary, Smali/resource counts, recent \
AssistantEvents, recent deterministic Findings already computed by a separate rule-based \
analyzer — do not re-derive those facts, just use them) and a conversation history, then a \
user question.

Respond with ONLY a JSON object:
{"mode": "finding" | "teaching" | "general",
 "message": "...",
 "observation": "...", "analysis": "...", "possible_problem": "...",
 "evidence": "...", "suggestion": "...", "confidence": "CONFIRMED_FACT" | "HYPOTHESIS" | "SUGGESTION" | ""}

Use mode "finding" (and fill observation/analysis/possible_problem/evidence/suggestion/confidence) \
only when responding to a concrete detected inconsistency or error. Use mode "teaching" for \
general learning questions (Android internals, Smali, security concepts) — just fill "message" \
with a clear, educational explanation, leave the other fields empty. Use mode "general" for \
anything else.

Hard rules:
- Never state that something IS an error when only a possibility exists — list the possible \
causes instead (mirror the style: "Posibles causas: 1... 2... 3...").
- Never claim causality between a modification and a failure unless the evidence is direct \
(e.g. the error message names the exact file/symbol the modification touched). Otherwise say \
a modification "podría estar relacionada", never "causó".
- Never claim you executed, modified, compiled, signed, or installed anything. You only ever \
explained or suggested.
- A HYPOTHESIS must never be phrased as a CONFIRMED_FACT.
Output JSON only, no prose, no markdown fences."""


class ClaudeAssistantProvider(AssistantProvider):
    """Real implementation using the Anthropic SDK. Requires
    ANTHROPIC_API_KEY — if unset, `answer()` raises immediately rather than
    silently no-op'ing (same convention as `app.ai.claude_provider.ClaudeProvider`).

    Deliberately: no `tools=` kwarg is ever passed to `messages.create()`.
    """

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            self._client = None
        else:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def answer(
        self,
        *,
        project_context: dict,
        history: list[AssistantTurn],
        question: str,
    ) -> AssistantAnswer:
        if self._client is None:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured; the assistant is disabled. "
                "Set it in your .env to enable it."
            )

        messages = [
            {"role": "user" if turn.role == "user" else "assistant", "content": turn.content}
            for turn in history
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    f"project_context:\n{json.dumps(project_context, indent=2)}\n\n"
                    f"question: {question}"
                ),
            }
        )

        message = self._client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )
        raw_text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        data = json.loads(raw_text)
        return AssistantAnswer(
            message=data.get("message", ""),
            mode=data.get("mode", "general"),
            observation=data.get("observation", ""),
            analysis=data.get("analysis", ""),
            possible_problem=data.get("possible_problem", ""),
            evidence=data.get("evidence", ""),
            suggestion=data.get("suggestion", ""),
            confidence=data.get("confidence", ""),
        )
