"""Builds a signed WebView-wrapper APK from a name+URL+icon+color — a
Python port of portal/generador de apks, integrated into this app's own
job queue so it actually runs on Railway (the PHP original's build.cmd/
launch_build() were Windows-only: PowerShell Start-Process, keytool.exe,
batch scripts). Signs with the SAME bundled keystore as signing_service.py
(backend/app/signing/release.jks, alias "webapp") so these apps and
APK-Lab-resigned apps carry one consistent certificate.

Workspace layout mirrors the PHP tool's so generator_apks.py (the read
side — list/icon/download/import) only needed its root path changed:
  storage_root/appgen/jobs/<slug>/{job.json, icon.<ext>, project/}
  storage_root/appgen/apks/<slug>.apk
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from app.core.config import get_settings
from app.core.security import run_tool, run_tool_streaming
from app.services import signing_service

settings = get_settings()

PACKAGE_PREFIX = "com.webapp."
KEY_ALIAS = "webapp"

_APPGEN_SOURCE_DIR = Path(__file__).resolve().parent.parent / "appgen"
_TEMPLATE_DIR = _APPGEN_SOURCE_DIR / "template"
_ICONGEN_JAVA = _APPGEN_SOURCE_DIR / "IconGen.java"

# Mirrors slugify()'s Java-reserved-word guard in the original PHP tool —
# a slug becomes part of a Java package name (com.webapp.<slug>).
_RESERVED_JAVA_WORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
    "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
    "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long", "native",
    "new", "package", "private", "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try", "void",
    "volatile", "while", "true", "false", "null",
}
_ACCENTS = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")


def jobs_dir() -> Path:
    path = settings.storage_root / "appgen" / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def apks_dir() -> Path:
    path = settings.storage_root / "appgen" / "apks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _gradle_user_home() -> Path:
    # On the persistent volume — without this, Gradle/AGP's several hundred
    # MB of Maven dependencies re-download on every single generated app
    # instead of once.
    path = settings.storage_root / "gradle-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(name: str) -> str:
    text = name.translate(_ACCENTS).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        text = "app"
    if text[0].isdigit():
        text = "a" + text
    if text in _RESERVED_JAVA_WORDS:
        text += "_app"
    return text[:40]


def package_id(slug: str) -> str:
    return PACKAGE_PREFIX + slug


def android_string(s: str) -> str:
    """Escapes text for an Android res/values/*.xml <string>."""
    s = s.replace("\\", "\\\\").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("'", "\\'").replace('"', '\\"')
    if s and s[0] in ("@", "?"):
        s = "\\" + s
    return s


def is_light_color(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def create_job(name: str, url: str, color: str, icon_bytes: bytes, icon_ext: str) -> dict:
    """Prepares the build workspace (template copy + generated config +
    icon) synchronously — the actual Gradle build happens in build_app(),
    called from the job worker so it goes through the normal job queue
    (progress/log streaming, failure handling) like every other job here."""
    slug = slugify(name)
    job_dir = jobs_dir() / slug
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True)

    project_dir = job_dir / "project"
    shutil.copytree(_TEMPLATE_DIR, project_dir)

    icon_ext = "jpg" if icon_ext.lower() == "jpeg" else (icon_ext.lower() or "png")
    (job_dir / f"icon.{icon_ext}").write_bytes(icon_bytes)

    version_code = int(time.time()) // 60  # grows over time -> lets a reinstall update in place
    version_name = time.strftime("1.%y%m%d.%H%M")
    pkg = package_id(slug)

    light_bar = "true" if is_light_color(color) else "false"
    config_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <string name="app_name">{android_string(name)}</string>\n'
        f'    <string name="start_url" translatable="false">{android_string(url)}</string>\n'
        f'    <color name="ic_launcher_background">{color}</color>\n'
        f'    <bool name="light_status_bar">{light_bar}</bool>\n'
        "</resources>\n"
    )
    (project_dir / "app" / "src" / "main" / "res" / "values" / "config.xml").write_text(config_xml)

    # Must be absolute: Gradle resolves a relative keystoreFile against the
    # project dir it's invoked with (project_dir, several levels below
    # storage_root), not wherever this process's cwd happens to be.
    keystore = signing_service.ensure_test_keystore().resolve()
    gradle_props = (
        f"appId={pkg}\nappVersionCode={version_code}\nappVersionName={version_name}\n"
        f"keystoreFile={keystore.as_posix()}\nkeystorePass={settings.test_keystore_password}\n"
        f"keyAlias={KEY_ALIAS}\nkeyPass={settings.test_key_password}\n"
    )
    with open(project_dir / "gradle.properties", "a", encoding="utf-8") as fh:
        fh.write(gradle_props)

    android_sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME", "/opt/android-sdk")
    (project_dir / "local.properties").write_text(f"sdk.dir={android_sdk_root}\n")

    info = {
        "slug": slug, "name": name, "url": url, "package": pkg, "color": color,
        "versionCode": version_code, "versionName": version_name, "created": time.time(),
    }
    (job_dir / "job.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
    return info


def build_app(slug: str, on_progress: Callable[[int, str], None]) -> dict:
    """Runs IconGen + `gradle assembleRelease` + copies the signed APK into
    apks_dir(). Raises on failure — job_worker.py's handler loop already
    turns any exception into a FAILED job with the error recorded."""
    job_dir = (jobs_dir() / slug).resolve()
    # Absolute — passed to Gradle both via `-p` and (indirectly) via cwd=
    # below; if storage_root is relative (the local-dev default) a relative
    # project_dir here gets resolved twice (once by cwd, once by -p) into a
    # nonsense doubled-up path.
    project_dir = (job_dir / "project").resolve()
    if not project_dir.is_dir():
        raise RuntimeError(f"No build workspace for {slug!r} (create_job must run first)")

    info = json.loads((job_dir / "job.json").read_text())
    icon_path = next(job_dir.glob("icon.*"), None)
    if not icon_path:
        raise RuntimeError("Missing icon for this build")

    on_progress(5, "Generando iconos...")
    res_dir = project_dir / "app" / "src" / "main" / "res"
    icon_result = run_tool(
        ["java", str(_ICONGEN_JAVA), str(icon_path), str(res_dir), info["color"]],
        timeout=60,
    )
    if icon_result.returncode != 0:
        raise RuntimeError(f"IconGen failed: {icon_result.stderr or icon_result.stdout}")

    on_progress(15, "Compilando APK con Gradle (puede tardar varios minutos la primera vez)...")
    gradle_bin = shutil.which("gradle") or "/opt/gradle/bin/gradle"
    env = {**os.environ, "GRADLE_USER_HOME": str(_gradle_user_home())}

    def on_line(line: str) -> None:
        on_progress(50, line[:200])

    result = run_tool_streaming(
        [gradle_bin, "-p", str(project_dir), "assembleRelease", "--console=plain", "--no-daemon"],
        on_line,
        timeout=settings.job_timeout_seconds,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError("Gradle build failed — see log above for details")

    on_progress(95, "Copiando APK...")
    built_apk = project_dir / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    if not built_apk.exists():
        raise RuntimeError("Build reported success but no APK was produced")
    out_path = apks_dir() / f"{slug}.apk"
    shutil.copyfile(built_apk, out_path)

    # project/ (source + Gradle's per-module build cache) isn't needed once
    # the signed APK is copied out — drop it to save volume space. The
    # shared Gradle dependency cache (_gradle_user_home()) is untouched.
    shutil.rmtree(project_dir, ignore_errors=True)

    on_progress(100, "Listo.")
    return {"slug": slug, "apk_path": str(out_path), **info}
