"""Optional device integration (spec section 5/25). Gated behind
device-detection: every endpoint using this must first call
`list_devices()` and handle the empty case gracefully — there is
deliberately no fallback/emulated success path.

Explicitly out of scope / never done automatically: `adb uninstall`. This
module never calls it.
"""
from __future__ import annotations

from pathlib import Path

from app.core.security import ProcessResult, run_tool
from app.tools.tool_manager import require


class DeviceError(Exception):
    pass


def list_devices() -> list[str]:
    adb = require("adb")
    result = run_tool([adb, "devices"], timeout=15)
    devices = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if line and "\t" in line:
            serial, status = line.split("\t", 1)
            if status.strip() == "device":
                devices.append(serial)
    return devices


def _require_device(serial: str) -> None:
    if serial not in list_devices():
        raise DeviceError(f"Device not connected or not authorized: {serial}")


def install(serial: str, apk_path: Path, *, timeout: int = 180) -> ProcessResult:
    _require_device(serial)
    adb = require("adb")
    return run_tool([adb, "-s", serial, "install", "-r", str(apk_path)], timeout=timeout)


def launch(serial: str, package: str, activity: str, *, timeout: int = 30) -> ProcessResult:
    _require_device(serial)
    adb = require("adb")
    component = f"{package}/{activity}"
    return run_tool(
        [adb, "-s", serial, "shell", "am", "start", "-n", component], timeout=timeout
    )


def logcat_snapshot(serial: str, package: str, *, lines: int = 500, timeout: int = 30) -> str:
    """Grabs a bounded logcat snapshot filtered to the project's package,
    rather than an unbounded live stream, to keep worker resource use
    predictable."""
    _require_device(serial)
    adb = require("adb")
    result = run_tool(
        [adb, "-s", serial, "logcat", "-d", "-t", str(lines)], timeout=timeout
    )
    full_log = result.stdout
    return "\n".join(line for line in full_log.splitlines() if package in line)
