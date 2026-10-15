from __future__ import annotations

import base64
from pathlib import Path

from app.core.security import resolve_safe_path, validate_simple_name
from app.services.change_types import ProposedChange


class ResourceError(Exception):
    pass


def propose_add_resource(
    decoded_dir: Path, rel_path: str, content: str, *, is_binary: bool = False
) -> ProposedChange:
    """`rel_path` e.g. 'res/values/strings.xml' or 'assets/notes.txt', relative
    to decoded_dir. When `is_binary` is True, `content` must already be
    base64-encoded (used for folder uploads of images/audio/etc.)."""
    for part in Path(rel_path).parts:
        validate_simple_name(part)
    target = resolve_safe_path(decoded_dir, rel_path)
    if target.exists():
        raise ResourceError(f"Resource already exists, use modify instead: {rel_path}")
    return ProposedChange(
        file=rel_path,
        operation="add_resource",
        description=f"Add resource {rel_path}",
        before_content="",
        after_content=content,
        is_binary=is_binary,
    )


def propose_modify_resource(
    decoded_dir: Path, rel_path: str, new_content: str, *, is_binary: bool = False
) -> ProposedChange:
    target = resolve_safe_path(decoded_dir, rel_path)
    if not target.exists():
        raise ResourceError(f"Resource not found: {rel_path}")
    before = (
        base64.b64encode(target.read_bytes()).decode("ascii")
        if is_binary
        else target.read_text(errors="ignore")
    )
    return ProposedChange(
        file=rel_path,
        operation="modify_resource",
        description=f"Modify resource {rel_path}",
        before_content=before,
        after_content=new_content,
        is_binary=is_binary,
    )
