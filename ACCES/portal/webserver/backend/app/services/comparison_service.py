"""Original vs rebuilt APK comparison (spec sections 16-17).

Distinguishes EXPECTED differences (META-INF, resources.arsc, signature,
zip ordering/compression/timestamps, apktool-generated internal names)
from IMPORTANT differences (removed classes/assets/resources/components,
missing methods, missing native libs) and renders a verdict.
"""
from __future__ import annotations

from pathlib import Path

from app.services import dex_service, manifest_service, signing_service, validation_service


def _manifest_component_names(manifest_data: dict, kind: str) -> set[str]:
    return {item["name"] for item in manifest_data.get(kind, [])}


def compare(
    original_apk: Path,
    rebuilt_apk: Path,
    original_decoded: Path,
    rebuilt_decoded: Path,
) -> dict:
    expected: list[str] = []
    important: list[str] = []
    summary: dict = {}

    # --- ZIP-level ---
    zip_diff = validation_service.classify_zip_diff(original_apk, rebuilt_apk)
    expected.extend(f"zip:{e}" for e in zip_diff["expected"])
    important.extend(f"zip entry removed: {e}" for e in zip_diff["removed_important"])
    summary["zip_added_files"] = zip_diff["added"]

    # --- DEX / Smali class & method counts ---
    orig_dex = dex_service.analyze_smali_trees(original_decoded)
    new_dex = dex_service.analyze_smali_trees(rebuilt_decoded)
    summary["classes"] = {"original": orig_dex["total_classes"], "rebuilt": new_dex["total_classes"]}
    summary["methods"] = {"original": orig_dex["total_methods"], "rebuilt": new_dex["total_methods"]}
    if new_dex["total_classes"] < orig_dex["total_classes"]:
        important.append(
            f"Class count decreased: {orig_dex['total_classes']} -> {new_dex['total_classes']}"
        )
    if new_dex["total_methods"] < orig_dex["total_methods"]:
        important.append(
            f"Method count decreased: {orig_dex['total_methods']} -> {new_dex['total_methods']}"
        )

    # --- Resources ---
    orig_res = dex_service.analyze_resources(original_decoded)
    new_res = dex_service.analyze_resources(rebuilt_decoded)
    summary["resources"] = {"original": orig_res["count"], "rebuilt": new_res["count"]}
    if new_res["count"] < orig_res["count"]:
        important.append(f"Resource count decreased: {orig_res['count']} -> {new_res['count']}")

    # --- Assets ---
    orig_assets = dex_service.analyze_assets(original_decoded)
    new_assets = dex_service.analyze_assets(rebuilt_decoded)
    summary["assets"] = {"original": orig_assets["count"], "rebuilt": new_assets["count"]}
    missing_assets = set(orig_assets["files"]) - set(new_assets["files"])
    if missing_assets:
        important.append(f"Assets removed: {sorted(missing_assets)}")

    # --- Native libraries ---
    orig_libs = set(dex_service.analyze_native_libs(original_decoded))
    new_libs = set(dex_service.analyze_native_libs(rebuilt_decoded))
    missing_libs = orig_libs - new_libs
    summary["native_libs"] = {"original": len(orig_libs), "rebuilt": len(new_libs)}
    if missing_libs:
        important.append(f"Native libraries missing: {sorted(missing_libs)}")

    # --- Manifest components ---
    orig_manifest = manifest_service.parse_manifest(original_decoded / "AndroidManifest.xml")
    new_manifest = manifest_service.parse_manifest(rebuilt_decoded / "AndroidManifest.xml")
    for kind in ("activities", "services", "receivers", "providers"):
        missing = _manifest_component_names(orig_manifest, kind) - _manifest_component_names(
            new_manifest, kind
        )
        if missing:
            important.append(f"{kind} removed: {sorted(missing)}")

    # --- Signature / certificate (always expected to differ with the lab test key) ---
    try:
        orig_cert = signing_service.certificate_info(original_apk)
        new_cert = signing_service.certificate_info(rebuilt_apk)
        if orig_cert.strip() != new_cert.strip():
            expected.append("signature: certificate differs (resigned with lab test key)")
        summary["signature_matches_original"] = orig_cert.strip() == new_cert.strip()
    except Exception as exc:  # original may be unsigned/unparseable — non-fatal
        summary["signature_check_error"] = str(exc)

    compatible = len(important) == 0
    return {
        "expected_differences": expected,
        "important_differences": important,
        "summary": summary,
        "compatible": compatible,
    }
