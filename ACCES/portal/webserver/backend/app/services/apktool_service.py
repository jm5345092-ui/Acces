from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from app.core.security import ProcessResult, run_tool, run_tool_streaming
from app.tools.tool_manager import require


def detect_version() -> str:
    apktool = require("apktool")
    result = run_tool([apktool, "--version"], timeout=20)
    return (result.stdout or result.stderr).strip()


# Heuristic progress estimation from apktool's own log output. apktool
# doesn't expose a real percentage anywhere — these are ordered stage
# markers (lowercase substrings of its "I: ..." log lines) mapped to an
# estimated percent, built from its typical decode/build log sequence.
# Good enough to turn "stuck at 0% until it's suddenly done" into real
# incremental feedback; not a precise measurement.
_DECODE_MARKERS: Sequence[tuple[str, int]] = (
    ("using apktool", 5),
    ("loading resource table", 12),
    ("decoding androidmanifest", 20),
    ("loading resource table from file", 25),
    ("regular manifest package", 28),
    ("decoding file-resources", 38),
    ("decoding values", 50),
    ("copying assets", 90),
    ("copying unknown files", 95),
    ("copying original files", 98),
)
_DECODE_GENERIC_MARKER = "baksmaling"
_DECODE_GENERIC_BAND = (52, 88)  # however many classesN.dex files there are

_BUILD_MARKERS: Sequence[tuple[str, int]] = (
    ("using apktool", 5),
    ("checking whether sources", 8),
    ("building resources", 55),
    ("building apk file", 85),
    ("copying unknown files", 95),
)
_BUILD_GENERIC_MARKER = "smal"  # "Smaling smali[_classesN] folder into classesN.dex..."
_BUILD_GENERIC_BAND = (10, 50)


def _stage_progress_parser(
    markers: Sequence[tuple[str, int]], generic_marker: str, generic_band: tuple[int, int]
) -> Callable[[str], int | None]:
    """Returns a stateful line -> percent-or-None parser: percent only
    increases, and only when a line crosses into a new, higher stage."""
    state = {"pct": 0}

    def handle(line: str) -> int | None:
        lowered = line.lower()
        for marker, pct in markers:
            if marker in lowered and pct > state["pct"]:
                state["pct"] = pct
                return pct
        if generic_marker in lowered:
            lo, hi = generic_band
            base = max(state["pct"], lo)
            nxt = round(base + (hi - base) * 0.3)
            if nxt > state["pct"]:
                state["pct"] = nxt
                return nxt
        return None

    return handle


def decode(
    apk_path: Path,
    out_dir: Path,
    *,
    timeout: int = 300,
    on_progress: Callable[[int, str], None] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> ProcessResult:
    apktool = require("apktool")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"{out_dir} is not empty; clear it before re-decoding")
    args = [apktool, "d", str(apk_path), "-o", str(out_dir), "-f"]
    if on_progress is None and on_line is None:
        return run_tool(args, timeout=timeout)

    parse = _stage_progress_parser(_DECODE_MARKERS, _DECODE_GENERIC_MARKER, _DECODE_GENERIC_BAND)

    def handle_line(line: str) -> None:
        if on_line is not None:
            on_line(line)
        if on_progress is not None:
            pct = parse(line)
            if pct is not None:
                on_progress(pct, line)

    return run_tool_streaming(args, handle_line, timeout=timeout)


def build(
    decoded_dir: Path,
    out_apk: Path,
    *,
    timeout: int = 300,
    on_progress: Callable[[int, str], None] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> ProcessResult:
    apktool = require("apktool")
    out_apk.parent.mkdir(parents=True, exist_ok=True)
    args = [apktool, "b", str(decoded_dir), "-o", str(out_apk)]
    if on_progress is None and on_line is None:
        return run_tool(args, timeout=timeout)

    parse = _stage_progress_parser(_BUILD_MARKERS, _BUILD_GENERIC_MARKER, _BUILD_GENERIC_BAND)

    def handle_line(line: str) -> None:
        if on_line is not None:
            on_line(line)
        if on_progress is not None:
            pct = parse(line)
            if pct is not None:
                on_progress(pct, line)

    return run_tool_streaming(args, handle_line, timeout=timeout)
