"""Resolves the absolute path to each external tool, failing loudly and
early rather than letting a missing binary surface as a confusing
subprocess error deep inside a service."""
from __future__ import annotations

import shutil


class ToolNotFoundError(Exception):
    pass


_REQUIRED = [
    "java",
    "apktool",
    "aapt2",
    "apksigner",
    "zipalign",
    "adb",
    "jadx",
    "keytool",
]


def require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ToolNotFoundError(
            f"Required tool '{tool}' was not found on PATH. "
            "This should only ever happen inside the worker container."
        )
    return path


def check_all() -> dict[str, bool]:
    return {tool: shutil.which(tool) is not None for tool in _REQUIRED}
