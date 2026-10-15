"""The structured Modification Engine (spec sections 10-12).

Every mutating operation is split into two phases:
  1. `propose_*` — validates input, locates the target, computes the new
     file content, and returns a diff WITHOUT writing anything to disk.
  2. `apply_pending` / `revert_pending` — actually writes `after_content`
     (or restores `before_content`), given a Modification row.

This keeps the "diff -> confirm -> apply" flow from spec section 12/13
enforceable at the API layer: nothing lands on disk until a Modification
row has been explicitly applied.
"""
from __future__ import annotations

import base64
from pathlib import Path

from app.core.security import (
    resolve_safe_path,
    validate_class_name,
    validate_package_name,
)
from app.services.change_types import ProposedChange
from app.services.smali_read_service import find_class_file, list_smali_modules

__all__ = [
    "ProposedChange",
    "find_class_file",
    "list_smali_modules",
    "ModificationError",
    "pick_module_for_new_class",
    "propose_create_smali_package",
    "propose_create_smali_class",
    "propose_insert_smali_instruction",
    "propose_replace_smali_block",
    "apply_change",
    "revert_change",
]


class ModificationError(Exception):
    pass


def _package_to_path(package: str) -> str:
    return package.replace(".", "/")


def _class_smali_skeleton(package: str, class_name: str) -> str:
    descriptor = f"L{_package_to_path(package)}/{class_name};"
    return (
        f".class public final {descriptor}\n"
        ".super Ljava/lang/Object;\n\n"
        ".method public constructor <init>()V\n"
        "    .locals 0\n\n"
        "    invoke-direct {p0}, Ljava/lang/Object;-><init>()V\n\n"
        "    return-void\n"
        ".end method\n"
    )


def pick_module_for_new_class(decoded_dir: Path, requested: str | None) -> str:
    modules = list_smali_modules(decoded_dir)
    if not modules:
        raise ModificationError("No smali module found; did you decode the APK first?")
    if requested:
        if requested not in modules:
            raise ModificationError(f"Unknown smali module: {requested}")
        return requested
    return modules[0]


def propose_create_smali_package(decoded_dir: Path, package: str) -> ProposedChange:
    validate_package_name(package)
    module = pick_module_for_new_class(decoded_dir, None)
    pkg_path = _package_to_path(package)
    target_dir = resolve_safe_path(decoded_dir, module, pkg_path)
    rel_marker = Path(module) / pkg_path / ".package"

    if target_dir.exists():
        raise ModificationError(f"Package already exists: {module}/{pkg_path}")

    # Directory-only change: `.package` is an empty marker file so the
    # (otherwise empty) package directory survives as a trackable,
    # revertible Modification instead of a bare mkdir with no record.
    return ProposedChange(
        file=str(rel_marker),
        operation="create_smali_package",
        description=f"Create Smali package {package} under {module}",
        before_content="",
        after_content="",
    )


def propose_create_smali_class(
    decoded_dir: Path, package: str, class_name: str, module: str | None = None
) -> ProposedChange:
    validate_package_name(package)
    validate_class_name(class_name)
    chosen_module = pick_module_for_new_class(decoded_dir, module)
    pkg_path = _package_to_path(package)
    rel_path = Path(chosen_module) / pkg_path / f"{class_name}.smali"
    target_file = resolve_safe_path(decoded_dir, str(rel_path))

    if target_file.exists():
        raise ModificationError(f"Class already exists: {rel_path}")

    content = _class_smali_skeleton(package, class_name)
    return ProposedChange(
        file=str(rel_path),
        operation="create_smali_class",
        description=f"Create class {package}.{class_name} in {chosen_module}",
        before_content="",
        after_content=content,
    )


def _find_method_span(lines: list[str], method_signature: str) -> tuple[int, int, int]:
    """Returns (header_idx, body_start_idx, end_idx) for `.method ... NAME(DESC)RET`
    matching `method_signature` like `onCreate(Landroid/os/Bundle;)V`."""
    name, _, desc_and_ret = method_signature.partition("(")
    desc_params, _, ret = desc_and_ret.partition(")")

    for idx, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped.startswith(".method") and stripped.endswith(f"{name}({desc_params}){ret}"):
            header_idx = idx
            body_start = idx + 1
            # Skip past .locals/.param/.annotation header lines to find true body start
            while body_start < len(lines) and lines[body_start].strip().startswith(
                (".locals", ".param", ".annotation", ".prologue")
            ):
                body_start += 1
            end_idx = None
            for j in range(idx, len(lines)):
                if lines[j].strip() == ".end method":
                    end_idx = j
                    break
            if end_idx is None:
                raise ModificationError(f"Malformed method, missing .end method: {method_signature}")
            return header_idx, body_start, end_idx
    raise ModificationError(f"Method not found: {method_signature}")


def propose_insert_smali_instruction(
    decoded_dir: Path,
    target_class: str,
    target_method: str,
    instruction: str,
    position: str = "start",
) -> ProposedChange:
    class_file = find_class_file(decoded_dir, target_class)
    original = class_file.read_text()
    lines = original.splitlines(keepends=True)

    header_idx, body_start, end_idx = _find_method_span(lines, target_method)
    insertion_point = body_start if position == "start" else end_idx

    new_lines = list(lines)
    indent = "    "
    new_lines.insert(insertion_point, f"{indent}{instruction}\n\n")
    new_content = "".join(new_lines)

    rel_path = class_file.relative_to(decoded_dir)
    return ProposedChange(
        file=str(rel_path),
        operation="insert_smali_instruction",
        description=f"Insert `{instruction}` at {position} of {target_method} in {rel_path}",
        before_content=original,
        after_content=new_content,
    )


def propose_replace_smali_block(
    decoded_dir: Path, target_class: str, search_block: str, replacement_block: str
) -> ProposedChange:
    class_file = find_class_file(decoded_dir, target_class)
    original = class_file.read_text()
    if search_block not in original:
        raise ModificationError("search_block not found in target class")
    new_content = original.replace(search_block, replacement_block, 1)

    rel_path = class_file.relative_to(decoded_dir)
    return ProposedChange(
        file=str(rel_path),
        operation="replace_smali_block",
        description=f"Replace block in {rel_path}",
        before_content=original,
        after_content=new_content,
    )


def apply_change(decoded_dir: Path, change: ProposedChange) -> None:
    target = resolve_safe_path(decoded_dir, change.file)
    if change.operation == "create_smali_package":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if change.is_binary:
        target.write_bytes(base64.b64decode(change.after_content))
    else:
        target.write_text(change.after_content)


_CREATION_OPERATIONS = {"create_smali_class", "create_smali_package", "add_resource"}


def revert_change(decoded_dir: Path, change: ProposedChange) -> None:
    target = resolve_safe_path(decoded_dir, change.file)
    if change.before_content == "" and change.operation in _CREATION_OPERATIONS:
        target.unlink(missing_ok=True)
        return
    if change.is_binary:
        target.write_bytes(base64.b64decode(change.before_content))
    else:
        target.write_text(change.before_content)
