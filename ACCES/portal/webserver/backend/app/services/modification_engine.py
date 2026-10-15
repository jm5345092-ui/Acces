"""Single dispatch point from a structured operation request (manual, from
the API, or AI-planned) to the right `propose_*` function (spec section
12). Both `api/modifications.py` and `api/ai.py` go through this so manual
and AI-driven edits are indistinguishable once proposed — same diff,
same confirm/apply/revert flow.
"""
from __future__ import annotations

from pathlib import Path

from app.services import manifest_service, resource_service, smali_service
from app.services.smali_service import ProposedChange

OPERATIONS = {
    "create_smali_package",
    "create_smali_class",
    "insert_smali_instruction",
    "replace_smali_block",
    "modify_manifest",
    "add_resource",
    "modify_resource",
}


class UnknownOperationError(Exception):
    pass


def propose(decoded_dir: Path, operation: str, params: dict) -> ProposedChange:
    if operation == "create_smali_package":
        return smali_service.propose_create_smali_package(decoded_dir, params["package"])

    if operation == "create_smali_class":
        return smali_service.propose_create_smali_class(
            decoded_dir, params["package"], params["class_name"], params.get("module")
        )

    if operation == "insert_smali_instruction":
        return smali_service.propose_insert_smali_instruction(
            decoded_dir,
            params["target_class"],
            params["target_method"],
            params["instruction"],
            params.get("position", "start"),
        )

    if operation == "replace_smali_block":
        return smali_service.propose_replace_smali_block(
            decoded_dir, params["target_class"], params["search_block"], params["replacement_block"]
        )

    if operation == "modify_manifest":
        manifest_path = decoded_dir / "AndroidManifest.xml"
        return manifest_service.propose_modify_manifest(
            manifest_path, params["xpath"], params["attribute"], params["value"]
        )

    if operation == "add_resource":
        return resource_service.propose_add_resource(
            decoded_dir, params["path"], params["content"], is_binary=params.get("is_binary", False)
        )

    if operation == "modify_resource":
        return resource_service.propose_modify_resource(
            decoded_dir, params["path"], params["content"], is_binary=params.get("is_binary", False)
        )

    raise UnknownOperationError(f"Unknown modification operation: {operation}")


def apply(decoded_dir: Path, change: ProposedChange) -> None:
    smali_service.apply_change(decoded_dir, change)


def revert(decoded_dir: Path, change: ProposedChange) -> None:
    smali_service.revert_change(decoded_dir, change)
