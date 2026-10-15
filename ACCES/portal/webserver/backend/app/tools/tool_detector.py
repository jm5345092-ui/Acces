"""Detects which Android/Java tooling is actually installed and working,
rather than hardcoding versions. Runs inside the worker container (the API
container has none of these tools by design)."""
from __future__ import annotations

import shutil
from dataclasses import dataclass

from app.core.security import ProcessResult, run_tool


@dataclass
class ToolStatus:
    name: str
    ok: bool
    version: str
    path: str | None


def _version_from(args: list[str]) -> ProcessResult | None:
    exe = shutil.which(args[0])
    if not exe:
        return None
    try:
        return run_tool([exe, *args[1:]], timeout=20)
    except Exception:
        return None


_CHECKS: dict[str, list[str]] = {
    "Java": ["java", "-version"],
    "Apktool": ["apktool", "--version"],
    "Android SDK (aapt2)": ["aapt2", "version"],
    "apksigner": ["apksigner", "version"],
    "zipalign": ["zipalign"],
    "ADB": ["adb", "version"],
    "JADX": ["jadx", "--version"],
}


def detect_all() -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for name, args in _CHECKS.items():
        exe = shutil.which(args[0])
        if not exe:
            statuses.append(ToolStatus(name=name, ok=False, version="", path=None))
            continue
        result = _version_from(args)
        if result is None:
            statuses.append(ToolStatus(name=name, ok=False, version="", path=exe))
            continue
        output = (result.stdout or result.stderr).strip().splitlines()
        version = output[0] if output else ""
        # zipalign has no --version flag; returncode 2 with usage text still
        # proves it's present and runnable.
        ok = result.returncode == 0 or (name == "zipalign" and exe is not None)
        statuses.append(ToolStatus(name=name, ok=ok, version=version[:120], path=exe))
    return statuses
