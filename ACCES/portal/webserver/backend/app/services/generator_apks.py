"""Read side of the app generator: lists/serves completed builds written by
appgen_service.build_app() to storage_root/appgen/{jobs,apks}/ — see that
module for the actual build. Kept as a separate read-only module since it's
also what api/generator.py's import-into-APK-Lab flow reads from.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.services import appgen_service

# Mirrors appgen_service.slugify()'s output charset.
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def is_valid_slug(slug: str) -> bool:
    return bool(slug) and bool(_SLUG_RE.match(slug))


def _jobs_dir() -> Path:
    return appgen_service.jobs_dir()


def _apks_dir() -> Path:
    return appgen_service.apks_dir()


def _icon_path(slug: str) -> Path | None:
    job_dir = _jobs_dir() / slug
    for ext in ("png", "jpg", "jpeg"):
        candidate = job_dir / f"icon.{ext}"
        if candidate.is_file():
            return candidate
    return None


def list_generator_apks() -> list[dict]:
    """Every generator build that finished (has an .apk on disk), newest
    first. Returns [] if the generator directory doesn't exist on this
    deployment rather than raising — it's a local-only tool."""
    jobs_dir = _jobs_dir()
    apks_dir = _apks_dir()
    if not jobs_dir.is_dir():
        return []

    entries = []
    for job_dir in jobs_dir.iterdir():
        slug = job_dir.name
        if not job_dir.is_dir() or not is_valid_slug(slug):
            continue
        apk_path = apks_dir / f"{slug}.apk"
        if not apk_path.is_file():
            continue

        info: dict = {}
        info_path = job_dir / "job.json"
        if info_path.is_file():
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                info = {}

        apk_stat = apk_path.stat()
        entries.append(
            {
                "slug": slug,
                "name": info.get("name") or slug,
                "package": info.get("package") or "",
                "color": info.get("color") or "#FFFFFF",
                "has_icon": _icon_path(slug) is not None,
                "size_bytes": apk_stat.st_size,
                "built_at": apk_stat.st_mtime,
            }
        )

    entries.sort(key=lambda e: e["built_at"], reverse=True)
    return entries


def generator_apk_path(slug: str) -> Path | None:
    if not is_valid_slug(slug):
        return None
    path = _apks_dir() / f"{slug}.apk"
    return path if path.is_file() else None


def generator_icon_path(slug: str) -> Path | None:
    if not is_valid_slug(slug):
        return None
    return _icon_path(slug)
