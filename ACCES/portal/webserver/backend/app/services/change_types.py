"""Shared data contract for a proposed-but-not-yet-applied modification.

Lives in its own module (not inside `smali_service.py`) so that read-only
consumers — `manifest_service.py`, `resource_service.py`, and eventually
the read-only assistant package — never need to import a module that also
contains write-capable functions (`apply_change`, `revert_change`, the
`propose_*` mutators) just to get this plain dataclass.
"""
from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass


@dataclass
class ProposedChange:
    file: str  # path relative to decoded_dir, for display/storage
    operation: str
    description: str
    before_content: str
    after_content: str
    # When True, before/after_content hold base64 (images, audio, etc. from
    # a folder upload) rather than text — a line-based diff doesn't apply.
    is_binary: bool = False

    @property
    def before_hash(self) -> str:
        return hashlib.sha256(self.before_content.encode()).hexdigest()

    @property
    def after_hash(self) -> str:
        return hashlib.sha256(self.after_content.encode()).hexdigest()

    @property
    def diff(self) -> str:
        if self.is_binary:
            return f"(archivo binario, {len(self.after_content)} bytes en base64 — sin diff de texto)"
        return "".join(
            difflib.unified_diff(
                self.before_content.splitlines(keepends=True),
                self.after_content.splitlines(keepends=True),
                fromfile=f"a/{self.file}",
                tofile=f"b/{self.file}",
            )
        )
