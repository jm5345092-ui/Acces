"""Keystore management. Never stores passwords in code or the database —
always read from environment/secrets.

Signs with the SAME keystore as portal/generador de apks (bundled at
app/signing/release.jks, alias "webapp") so every APK this project touches
— generator-built or APK-Lab-rebuilt — carries one consistent signature and
can be installed over the other. settings.test_key_alias/*_password must
match that keystore's actual alias/password (see keystore.properties next
to the source file in the generator's keys/ dir — never committed here)."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.security import ProcessResult, run_tool
from app.tools.tool_manager import require

settings = get_settings()

BUNDLED_KEYSTORE = Path(__file__).resolve().parent.parent / "signing" / "release.jks"


def test_keystore_path(storage_root: Path) -> Path:
    path = storage_root / "keys" / "apklab-test.keystore"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_test_keystore() -> Path:
    path = test_keystore_path(settings.storage_root)

    if BUNDLED_KEYSTORE.exists():
        # Re-copy every time (cheap, idempotent) so the deployed keystore
        # can never silently drift from the bundled source of truth.
        shutil.copyfile(BUNDLED_KEYSTORE, path)
        return path

    if path.exists():
        return path

    # Bundled keystore missing (shouldn't happen in this repo) — fall back
    # to generating a throwaway lab key so signing still works.
    keytool = require("keytool")
    run_tool(
        [
            keytool,
            "-genkeypair",
            "-keystore", str(path),
            "-alias", settings.test_key_alias,
            "-storepass", settings.test_keystore_password,
            "-keypass", settings.test_key_password,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-dname", "CN=APK-Lab Test, OU=Lab, O=APK-Lab, L=NA, S=NA, C=NA",
        ],
        timeout=60,
    )
    return path


def sign(unsigned_apk: Path, signed_apk: Path, *, timeout: int = 120) -> ProcessResult:
    apksigner = require("apksigner")
    keystore = ensure_test_keystore()
    signed_apk.parent.mkdir(parents=True, exist_ok=True)
    return run_tool(
        [
            apksigner, "sign",
            "--ks", str(keystore),
            "--ks-pass", f"pass:{settings.test_keystore_password}",
            "--ks-key-alias", settings.test_key_alias,
            "--key-pass", f"pass:{settings.test_key_password}",
            "--out", str(signed_apk),
            str(unsigned_apk),
        ],
        timeout=timeout,
    )


def verify(apk_path: Path, *, timeout: int = 60) -> ProcessResult:
    apksigner = require("apksigner")
    return run_tool([apksigner, "verify", "--verbose", str(apk_path)], timeout=timeout)


def zipalign(unaligned_apk: Path, aligned_apk: Path, *, timeout: int = 60) -> ProcessResult:
    tool = require("zipalign")
    aligned_apk.parent.mkdir(parents=True, exist_ok=True)
    return run_tool([tool, "-f", "-p", "4", str(unaligned_apk), str(aligned_apk)], timeout=timeout)


def certificate_info(apk_path: Path, *, timeout: int = 60) -> str:
    apksigner = require("apksigner")
    result = run_tool([apksigner, "verify", "--print-certs", str(apk_path)], timeout=timeout)
    return result.stdout or result.stderr
