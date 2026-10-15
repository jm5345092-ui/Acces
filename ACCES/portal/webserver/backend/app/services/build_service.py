"""Orchestrates the rebuild pipeline (spec section 14):

  decoded -> apktool build -> unsigned APK -> zipalign -> aligned APK
  -> apksigner sign -> signed APK -> apksigner verify -> final APK

Each stage reports progress via the `on_progress(pct, message)` callback so
the caller (job_worker) can push live updates over the job's log/SSE
channel.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.services import apktool_service, signing_service

ProgressCB = Callable[[int, str], None]


class BuildError(Exception):
    pass


def run_pipeline(
    decoded_dir: Path,
    rebuild_dir: Path,
    signed_dir: Path,
    on_progress: ProgressCB,
    on_line: Callable[[str], None] | None = None,
) -> dict:
    on_progress(5, "Starting apktool build...")
    unsigned_apk = rebuild_dir / "unsigned.apk"

    def remapped_progress(pct: int, message: str) -> None:
        # apktool's own 0-100 estimate for just the build stage -> this
        # pipeline's 5-38% band, leaving room for the 40% "complete" marker.
        on_progress(min(5 + round(pct * 0.33), 38), message)

    result = apktool_service.build(
        decoded_dir, unsigned_apk, on_progress=remapped_progress, on_line=on_line
    )
    if result.returncode != 0:
        raise BuildError(f"apktool build failed:\n{result.stderr or result.stdout}")
    on_progress(40, "apktool build complete.")

    on_progress(45, "Running zipalign...")
    aligned_apk = rebuild_dir / "aligned.apk"
    result = signing_service.zipalign(unsigned_apk, aligned_apk)
    if result.returncode != 0:
        raise BuildError(f"zipalign failed:\n{result.stderr or result.stdout}")
    on_progress(60, "zipalign complete.")

    on_progress(65, "Signing with lab test key...")
    signed_apk = signed_dir / "signed.apk"
    result = signing_service.sign(aligned_apk, signed_apk)
    if result.returncode != 0:
        raise BuildError(f"Signing failed:\n{result.stderr or result.stdout}")
    on_progress(85, "Signing complete.")

    on_progress(90, "Verifying signature...")
    result = signing_service.verify(signed_apk)
    if result.returncode != 0:
        raise BuildError(f"Signature verification failed:\n{result.stderr or result.stdout}")
    on_progress(100, "Build pipeline complete.")

    return {
        "unsigned_apk": str(unsigned_apk),
        "aligned_apk": str(aligned_apk),
        "signed_apk": str(signed_apk),
        "verify_output": result.stdout,
    }
