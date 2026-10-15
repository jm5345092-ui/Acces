"""Structural read-only guarantee (architecture review plan §10/§14, tests
A-G, J): every module under `app/assistant/` may only import from a small,
explicit allowlist. This is a default-deny test — anything not listed is
rejected, including future additions — rather than a blocklist that only
catches names we thought to forbid.

`app/api/assistant.py` gets a separate, narrower blocklist check (it
legitimately needs FastAPI/DB-session plumbing that `app/assistant/`
itself must not import) as defense-in-depth on top of the allowlist.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ASSISTANT_PKG = Path(__file__).resolve().parent.parent / "app" / "assistant"
API_ASSISTANT_FILE = Path(__file__).resolve().parent.parent / "app" / "api" / "assistant.py"

# Anything imported from `app.*` by `app/assistant/*.py` must start with one
# of these. Stdlib / third-party imports are allowed except for the
# explicit `subprocess` ban below (no legitimate read-only use needs it).
ALLOWED_APP_PREFIXES = (
    "app.assistant",  # internal submodules of the package itself
    "app.core.config",
    "app.core.db",
    "app.core.security",
    "app.models.assistant",
    "app.models.job",
    "app.models.modification",
    "app.models.project",
    "app.services.manifest_service",
    "app.services.dex_service",
    "app.services.smali_read_service",
    "app.services.change_types",
)

FORBIDDEN_ANYWHERE = {
    "subprocess",
    "app.services.modification_engine",
    "app.services.build_service",
    "app.services.apktool_service",
    "app.services.signing_service",
    "app.services.adb_service",
    "app.services.smali_service",
    "app.services.resource_service",
    "app.services.apk_service",
    "app.services.comparison_service",
    "app.services.validation_service",
    "app.core.security.run_tool",
}


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            # Record `from X import Y` as "X.Y" (never the bare "X") so a
            # forbidden function-level import (e.g.
            # `from app.core.security import run_tool`) is caught even
            # though the module `app.core.security` itself is allowed, and
            # a package re-export (`from app.services import dex_service`)
            # is judged on the specific submodule, not the parent package.
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _assistant_py_files() -> list[Path]:
    return sorted(ASSISTANT_PKG.glob("*.py"))


@pytest.mark.parametrize("path", _assistant_py_files(), ids=lambda p: p.name)
def test_assistant_module_imports_are_allowlisted(path: Path):
    for name in _imported_names(path):
        assert name not in FORBIDDEN_ANYWHERE, f"{path.name} imports forbidden symbol: {name}"

        if not name.startswith("app."):
            continue  # stdlib / third-party — fine except the explicit bans above

        allowed = any(name == p or name.startswith(p + ".") for p in ALLOWED_APP_PREFIXES)
        assert allowed, f"{path.name} imports non-allowlisted app module: {name}"


def test_api_assistant_router_has_no_write_capable_imports():
    for name in _imported_names(API_ASSISTANT_FILE):
        assert name not in FORBIDDEN_ANYWHERE, f"api/assistant.py imports forbidden symbol: {name}"
