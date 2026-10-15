"""Pure read-only Smali tree helpers.

Deliberately separate from `smali_service.py` (which also contains
`apply_change`/`revert_change`/the `propose_*` write mutators) so that a
read-only consumer — most importantly the assistant package in
`app/assistant/` — can import exactly this module and get zero write
capability by construction, instead of having to "promise" not to call the
write functions that would otherwise live right next to these.

This module must never import anything from `smali_service.py` (the
dependency only goes the other way: `smali_service.py` re-exports from
here for backward compatibility). It must never import `subprocess` or
`app.core.security.run_tool`.
"""
from __future__ import annotations

from pathlib import Path

from app.core.security import InvalidIdentifierError, resolve_safe_path


class ClassNotFoundError(Exception):
    """Raised when a target class cannot be located in any smali module."""


def list_smali_modules(decoded_dir: Path) -> list[str]:
    return sorted(p.name for p in decoded_dir.glob("smali*") if p.is_dir())


def find_class_file(decoded_dir: Path, target_class: str) -> Path:
    """`target_class` is a dotted or slashed class name, e.g.
    'com.example.app.MainActivity' or 'com/example/app/MainActivity'."""
    rel = target_class.replace(".", "/")
    if rel.startswith("/"):
        raise InvalidIdentifierError("target_class must not be absolute")
    for module in list_smali_modules(decoded_dir):
        candidate = resolve_safe_path(decoded_dir, module, f"{rel}.smali")
        if candidate.exists():
            return candidate
    raise ClassNotFoundError(f"Smali class not found in any module: {target_class}")


def class_exists(decoded_dir: Path, target_class: str) -> bool:
    try:
        find_class_file(decoded_dir, target_class)
        return True
    except ClassNotFoundError:
        return False
