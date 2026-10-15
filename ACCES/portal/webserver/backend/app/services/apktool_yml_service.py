"""Reads `apktool.yml`, written by `apktool d` alongside the decoded tree.

apktool frequently does NOT keep a `<uses-sdk>` element in the decoded
`AndroidManifest.xml` — for many modern (Gradle/AGP-built) APKs it moves
minSdkVersion/targetSdkVersion (and the app's versionCode/versionName)
into `apktool.yml`'s `sdkInfo`/`versionInfo` sections instead, to work
around an old ambiguity bug. `manifest_service.parse_manifest()` alone
therefore returns blank min_sdk/target_sdk/version_code/version_name for
many real-world APKs — this is the fallback/primary source for that info.

Pure read, no subprocess — safe to reuse anywhere a decoded project is read.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def parse_apktool_yml(decoded_dir: Path) -> dict:
    path = decoded_dir / "apktool.yml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return {}

    sdk_info = data.get("sdkInfo") or {}
    version_info = data.get("versionInfo") or {}

    return {
        "apktool_version": str(data.get("version", "")),
        "min_sdk": str(sdk_info.get("minSdkVersion", "")),
        "target_sdk": str(sdk_info.get("targetSdkVersion", "")),
        "compile_sdk": str(sdk_info.get("compileSdkVersion", "")),
        "version_code": str(version_info.get("versionCode", "")),
        "version_name": str(version_info.get("versionName", "")),
    }


def enrich_manifest_with_apktool_yml(manifest: dict, decoded_dir: Path) -> dict:
    """`manifest` is the dict from `manifest_service.parse_manifest()`.
    Fills in min_sdk/target_sdk/version_code/version_name from apktool.yml
    whenever the manifest-parsed value is blank (the common case for
    Gradle/AGP-built APKs — see module docstring), and always adds
    compile_sdk/apktool_version, which only ever live in apktool.yml."""
    yml = parse_apktool_yml(decoded_dir)
    enriched = dict(manifest)
    for key in ("min_sdk", "target_sdk", "version_code", "version_name"):
        if not enriched.get(key) and yml.get(key):
            enriched[key] = yml[key]
    enriched["compile_sdk"] = yml.get("compile_sdk", "")
    enriched["apktool_version"] = yml.get("apktool_version", "")
    return enriched
