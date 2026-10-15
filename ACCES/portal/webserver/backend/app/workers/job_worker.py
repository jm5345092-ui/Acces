"""The worker process loop. This is the ONLY place in the codebase that
actually invokes apktool/aapt2/apksigner/zipalign/adb/jadx against
untrusted, uploaded APK content — it runs in the `worker` container
(see worker/Dockerfile) as a non-root user, separate from the `api`
container which has none of these tools installed.
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from app.assistant import events as assistant_events
from app.core.config import get_settings
from app.core.db import SessionLocal, init_db
from app.core.logging import configure_logging, get_logger
from app.jobqueue import default_queue
from app.models.job import Job, JobType
from app.models.project import Project, ProjectStatus
from app.services import (
    adb_service,
    apk_service,
    appgen_service,
    apktool_service,
    apktool_yml_service,
    build_service,
    comparison_service,
    dex_service,
    manifest_service,
)
from app.tools.tool_detector import detect_all

settings = get_settings()
logger = get_logger("job_worker")


def _project(project_id: str | None) -> Project | None:
    if not project_id:
        return None
    db = SessionLocal()
    try:
        return db.get(Project, project_id)
    finally:
        db.close()


def _update_project(project_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if not project:
            return
        for key, value in fields.items():
            setattr(project, key, value)
        db.commit()
    finally:
        db.close()


def handle_decode(job: dict) -> dict:
    project_id = job["project_id"]
    root = apk_service.project_root(project_id)
    original_apk = root / "original" / "original.apk"
    decoded_dir = root / "decoded"

    default_queue.append_log(job["id"], f"Decoding {original_apk.name} with apktool...")
    apk_service.clear_dir(decoded_dir)
    _update_project(project_id, status=ProjectStatus.DECODING)
    default_queue.set_progress(job["id"], 1)

    result = apktool_service.decode(
        original_apk,
        decoded_dir,
        on_progress=lambda pct, _msg: default_queue.set_progress(job["id"], pct),
        on_line=lambda line: default_queue.append_log(job["id"], line),
    )
    if result.returncode != 0:
        _update_project(project_id, status=ProjectStatus.FAILED)
        raise RuntimeError(f"apktool decode failed: {result.stderr or result.stdout}")

    manifest_path = decoded_dir / "AndroidManifest.xml"
    manifest = manifest_service.parse_manifest(manifest_path) if manifest_path.exists() else {}
    # apktool often moves minSdk/targetSdk/versionCode/versionName out of
    # the decoded manifest into apktool.yml for modern (Gradle-built) APKs
    # — fall back to that when the manifest alone comes back blank.
    manifest = apktool_yml_service.enrich_manifest_with_apktool_yml(manifest, decoded_dir)
    _update_project(
        project_id,
        status=ProjectStatus.DECODED,
        package_name=manifest.get("package", ""),
        version_code=str(manifest.get("version_code", "")),
        version_name=str(manifest.get("version_name", "")),
        min_sdk=str(manifest.get("min_sdk", "")),
        target_sdk=str(manifest.get("target_sdk", "")),
    )
    default_queue.append_log(job["id"], "Decode complete.")
    return {"manifest": manifest}


def handle_analyze(job: dict) -> dict:
    project_id = job["project_id"]
    root = apk_service.project_root(project_id)
    decoded_dir = root / "decoded"
    original_apk = root / "original" / "original.apk"

    default_queue.append_log(job["id"], "Running analysis...")
    _update_project(project_id, status=ProjectStatus.ANALYZING)
    default_queue.set_progress(job["id"], 5)

    manifest_path = decoded_dir / "AndroidManifest.xml"
    manifest = manifest_service.parse_manifest(manifest_path)
    manifest = apktool_yml_service.enrich_manifest_with_apktool_yml(manifest, decoded_dir)
    entry_point = manifest_service.find_entry_point(manifest_path, decoded_dir)
    default_queue.set_progress(job["id"], 20)

    dex = dex_service.analyze_smali_trees(decoded_dir)
    default_queue.set_progress(job["id"], 50)

    resources = dex_service.analyze_resources(decoded_dir)
    default_queue.set_progress(job["id"], 65)

    assets = dex_service.analyze_assets(decoded_dir)
    native_libs = dex_service.analyze_native_libs(decoded_dir)
    default_queue.set_progress(job["id"], 80)

    from app.services import signing_service

    try:
        certificate = signing_service.certificate_info(original_apk)
    except Exception as exc:
        certificate = f"(unavailable: {exc})"
    default_queue.set_progress(job["id"], 95)

    report = {
        "manifest": manifest,
        "entry_point": entry_point,
        "dex": dex,
        "resources": resources,
        "assets": assets,
        "native_libs": native_libs,
        "certificate": certificate,
    }
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "analysis.json").write_text(json.dumps(report, indent=2))
    _update_project(project_id, status=ProjectStatus.ANALYZED)
    default_queue.append_log(job["id"], "Analysis complete.")
    return report


def handle_build_pipeline(job: dict) -> dict:
    project_id = job["project_id"]
    root = apk_service.project_root(project_id)
    decoded_dir = root / "decoded"
    rebuild_dir = root / "rebuild"
    signed_dir = root / "signed"
    apk_service.clear_dir(rebuild_dir)
    apk_service.clear_dir(signed_dir)

    _update_project(project_id, status=ProjectStatus.BUILDING)

    def on_progress(pct: int, message: str) -> None:
        default_queue.set_progress(job["id"], pct)
        default_queue.append_log(job["id"], message)

    result = build_service.run_pipeline(decoded_dir, rebuild_dir, signed_dir, on_progress)
    _update_project(project_id, status=ProjectStatus.SIGNED)

    default_queue.append_log(job["id"], "Decoding rebuilt APK for comparison...")
    rebuilt_decoded = root / "temp" / "rebuilt_decoded"
    apk_service.clear_dir(rebuilt_decoded)
    decode_result = apktool_service.decode(Path(result["signed_apk"]), rebuilt_decoded)
    if decode_result.returncode != 0:
        default_queue.append_log(job["id"], "Warning: could not decode rebuilt APK for comparison.")
        return result

    comparison = comparison_service.compare(
        original_apk=root / "original" / "original.apk",
        rebuilt_apk=Path(result["signed_apk"]),
        original_decoded=decoded_dir,
        rebuilt_decoded=rebuilt_decoded,
    )
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "comparison.json").write_text(json.dumps(comparison, indent=2))
    default_queue.append_log(
        job["id"],
        "MODIFICACIÓN COMPATIBLE" if comparison["compatible"] else "DIFERENCIAS IMPORTANTES DETECTADAS",
    )

    db = SessionLocal()
    try:
        assistant_events.record_comparison_event(
            db, project_id, job["id"], comparison.get("important_differences", [])
        )
    finally:
        db.close()

    return {**result, "comparison": comparison}


def handle_device_list(job: dict) -> dict:
    return {"devices": adb_service.list_devices()}


def handle_device_install(job: dict) -> dict:
    project_id = job["project_id"]
    serial = job["payload"]["serial"]
    signed_apk = apk_service.project_root(project_id) / "signed" / "signed.apk"
    if not signed_apk.exists():
        raise RuntimeError("No signed APK yet; run the build pipeline first")
    result = adb_service.install(serial, signed_apk)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return {"output": result.stdout}


def handle_device_launch(job: dict) -> dict:
    project_id = job["project_id"]
    serial = job["payload"]["serial"]
    project = _project(project_id)
    decoded_dir = apk_service.project_root(project_id) / "decoded"
    manifest_path = decoded_dir / "AndroidManifest.xml"
    main_activity = manifest_service.find_main_activity(manifest_path)
    if not main_activity or not project:
        raise RuntimeError("Could not determine the main (launcher) Activity")
    activity_class = manifest_service.resolve_activity_class(project.package_name, main_activity)
    result = adb_service.launch(serial, project.package_name, activity_class)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return {"output": result.stdout}


def handle_device_logcat(job: dict) -> dict:
    project_id = job["project_id"]
    serial = job["payload"]["serial"]
    project = _project(project_id)
    log = adb_service.logcat_snapshot(serial, project.package_name if project else "")
    return {"log": log}


def handle_generate_app(job: dict) -> dict:
    slug = job["payload"]["slug"]

    def on_progress(pct: int, message: str) -> None:
        default_queue.set_progress(job["id"], pct)
        default_queue.append_log(job["id"], message)

    return appgen_service.build_app(slug, on_progress)


def handle_tool_check(job: dict) -> dict:
    statuses = [asdict(t) for t in detect_all()]
    payload = {"tools": statuses, "checked_at": time.time()}
    (settings.storage_root).mkdir(parents=True, exist_ok=True)
    (settings.storage_root / "tool_status.json").write_text(json.dumps(payload, indent=2))
    return payload


_HANDLERS = {
    JobType.DECODE: handle_decode,
    JobType.ANALYZE: handle_analyze,
    JobType.BUILD_PIPELINE: handle_build_pipeline,
    JobType.DEVICE_LIST: handle_device_list,
    JobType.DEVICE_INSTALL: handle_device_install,
    JobType.DEVICE_LAUNCH: handle_device_launch,
    JobType.DEVICE_LOGCAT: handle_device_logcat,
    JobType.TOOL_CHECK: handle_tool_check,
    JobType.GENERATE_APP: handle_generate_app,
}


def run_forever() -> None:
    configure_logging()
    init_db()
    logger.info("APK-Lab worker started; polling for jobs...")
    while True:
        job = default_queue.claim_next()
        if not job:
            default_queue.poll_loop_sleep()
            continue

        logger.info("Claimed job %s (%s)", job["id"], job["type"])
        try:
            handler = _HANDLERS[JobType(job["type"])]
            result = handler(job)
            default_queue.complete(job["id"], result)
        except Exception as exc:  # noqa: BLE001 — a bad APK must not kill the worker loop
            logger.error("Job %s failed: %s\n%s", job["id"], exc, traceback.format_exc())
            default_queue.append_log(job["id"], f"ERROR: {exc}")
            default_queue.fail(job["id"], str(exc))
            if job.get("project_id"):
                db = SessionLocal()
                try:
                    job_row = db.get(Job, job["id"])
                    if job_row:
                        assistant_events.record_job_event(db, job_row, str(exc))
                finally:
                    db.close()


if __name__ == "__main__":
    run_forever()
