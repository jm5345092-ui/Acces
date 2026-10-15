"""Plan §14 test J: ProjectAnalyzer only consumes read-only interfaces.

Complements the import-allowlist test (which already covers analyzer.py)
with two different angles:
  1. Static: analyzer.py never reaches past its context's public interface
     into a private attribute (e.g. `self._ctx._db`, `self._ctx._project_root`).
  2. Behavioral: running the analyzer against a context object that has
     ONLY the read methods it needs (no `commit`/`add`/`session`/`db`
     attribute at all) succeeds — if the analyzer ever attempted a write
     call, this would raise AttributeError.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.assistant.analyzer import ProjectAnalyzer
from tests.test_assistant_analyzer_findings import MANIFEST_WITH_ACTIVITY, FakeContext

ANALYZER_FILE = Path(__file__).resolve().parent.parent / "app" / "assistant" / "analyzer.py"

_PRIVATE_ATTR_CHAIN_RE = re.compile(r"\._ctx\._\w|\bctx\._\w")


def test_analyzer_never_reaches_into_context_internals():
    source = ANALYZER_FILE.read_text(encoding="utf-8")
    assert not _PRIVATE_ATTR_CHAIN_RE.search(source), (
        "analyzer.py appears to access a private attribute of its context "
        "(e.g. `self._ctx._db`) instead of going through its public "
        "read-only methods."
    )

    # Also: no attribute access anywhere in the file targets a name that
    # looks like a write primitive, even indirectly.
    tree = ast.parse(source, filename=str(ANALYZER_FILE))
    write_like = {"commit", "add", "flush", "delete", "write_text", "write_bytes", "unlink"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in write_like, f"analyzer.py calls a write-like method: .{node.attr}(...)"


def test_analyzer_runs_against_a_context_with_no_write_surface_at_all():
    """FakeContext (from test_assistant_analyzer_findings) defines ONLY the
    read methods ProjectAnalyzer needs — no `db`, `commit`, `add`, or
    `session`. If ProjectAnalyzer ever tried to write, this would raise
    AttributeError instead of returning normally."""
    assert not hasattr(FakeContext, "commit")
    assert not hasattr(FakeContext, "add")
    assert not hasattr(FakeContext, "db")
    assert not hasattr(FakeContext, "session")

    ctx = FakeContext(manifest=MANIFEST_WITH_ACTIVITY, existing_classes=())
    findings = ProjectAnalyzer(ctx).analyze()
    assert isinstance(findings, list)  # ran to completion, read-only
