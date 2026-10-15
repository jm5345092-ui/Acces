"""Workspace lifecycle for a single APK project.

Layout (see plan): storage/projects/<project_id>/{original,decoded,
modifications,rebuild,signed,logs,reports,temp}/ + metadata.json.
`original/original.apk` is written exactly once and immediately made
read-only; nothing in this codebase is allowed to open it for writing
again (enforced via core.security.assert_not_original).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.security import ReadOnlyViolationError, resolve_safe_path

settings = get_settings()

WORKSPACE_SUBDIRS = (
    "original",
    "decoded",
    "modifications",
    "rebuild",
    "signed",
    "logs",
    "reports",
    "temp",
)


def project_root(project_id: str) -> Path:
    # project_id is always server-generated (uuid4().hex) — see
    # core.security.new_project_id — so this join is inherently safe, but we
    # still run it through resolve_safe_path for defense in depth.
    return resolve_safe_path(settings.projects_root, project_id)


def original_apk_path(project_id: str) -> Path:
    return project_root(project_id) / "original" / "original.apk"


def init_workspace(project_id: str) -> Path:
    root = settings.projects_root / project_id
    for sub in WORKSPACE_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _hash_stream(fh: BinaryIO, algo: str) -> str:
    fh.seek(0)
    h = hashlib.new(algo)
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        h.update(chunk)
    fh.seek(0)
    return h.hexdigest()


def save_original_upload(project_id: str, upload_stream: BinaryIO, max_bytes: int) -> dict:
    root = init_workspace(project_id)
    dest = root / "original" / "original.apk"
    if dest.exists():
        raise ReadOnlyViolationError("This project already has an original APK.")

    size = 0
    with open(dest, "wb") as out:
        while chunk := upload_stream.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"Upload exceeds max size of {max_bytes} bytes")
            out.write(chunk)

    with open(dest, "rb") as fh:
        sha256 = _hash_stream(fh, "sha256")
        sha1 = _hash_stream(fh, "sha1")

    # Make the original read-only at the filesystem level too.
    os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP)

    metadata = {
        "project_id": project_id,
        "sha256": sha256,
        "sha1": sha1,
        "size_bytes": size,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    write_metadata(project_id, metadata)
    return metadata


def save_original_from_path(project_id: str, source: Path, max_bytes: int) -> dict:
    """Same contract as save_original_upload, but copies from a local file
    already on this filesystem (the generator-apks import flow) instead of
    reading an upload stream."""
    root = init_workspace(project_id)
    dest = root / "original" / "original.apk"
    if dest.exists():
        raise ReadOnlyViolationError("This project already has an original APK.")

    size = source.stat().st_size
    if size > max_bytes:
        raise ValueError(f"Source APK exceeds max size of {max_bytes} bytes")
    shutil.copyfile(source, dest)

    with open(dest, "rb") as fh:
        sha256 = _hash_stream(fh, "sha256")
        sha1 = _hash_stream(fh, "sha1")

    os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP)

    metadata = {
        "project_id": project_id,
        "sha256": sha256,
        "sha1": sha1,
        "size_bytes": size,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    write_metadata(project_id, metadata)
    return metadata


def metadata_path(project_id: str) -> Path:
    return project_root(project_id) / "metadata.json"


def write_metadata(project_id: str, data: dict) -> None:
    path = metadata_path(project_id)
    existing = read_metadata(project_id)
    existing.update(data)
    path.write_text(json.dumps(existing, indent=2))


def read_metadata(project_id: str) -> dict:
    path = metadata_path(project_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def clear_dir(path: Path) -> None:
    """Safely wipe a directory's contents (used before re-decoding), never
    the original/ directory."""
    if path.name == "original":
        raise ReadOnlyViolationError("Refusing to clear the original/ directory.")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
