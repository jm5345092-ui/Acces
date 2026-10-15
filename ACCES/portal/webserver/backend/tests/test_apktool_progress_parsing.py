"""apktool exposes no real progress percentage — `_stage_progress_parser`
estimates one from its own log line sequence. Pure function, no
subprocess, tested directly against representative decode/build output."""
from __future__ import annotations

from app.services.apktool_service import (
    _BUILD_GENERIC_BAND,
    _BUILD_GENERIC_MARKER,
    _BUILD_MARKERS,
    _DECODE_GENERIC_BAND,
    _DECODE_GENERIC_MARKER,
    _DECODE_MARKERS,
    _stage_progress_parser,
)

DECODE_LOG = [
    "I: Using Apktool 2.9.3 on original.apk",
    "I: Loading Resource Table...",
    "I: Decoding AndroidManifest.xml with resources...",
    "I: Loading Resource Table from file: /home/apklab/.local/share/apktool/framework/1.apk",
    "I: Regular manifest package...",
    "I: Decoding file-resources...",
    "I: Decoding values */* XMLs...",
    "I: Baksmaling classes.dex...",
    "I: Baksmaling classes2.dex...",
    "I: Baksmaling classes3.dex...",
    "I: Copying assets and libs...",
    "I: Copying unknown files...",
    "I: Copying original files...",
]


def test_decode_progress_is_monotonically_non_decreasing():
    parse = _stage_progress_parser(_DECODE_MARKERS, _DECODE_GENERIC_MARKER, _DECODE_GENERIC_BAND)
    seen = []
    for line in DECODE_LOG:
        pct = parse(line)
        if pct is not None:
            seen.append(pct)
    assert seen == sorted(seen)
    assert seen[0] == 5  # "Using Apktool"
    assert seen[-1] == 98  # "Copying original files"


def test_decode_progress_handles_unknown_lines_gracefully():
    parse = _stage_progress_parser(_DECODE_MARKERS, _DECODE_GENERIC_MARKER, _DECODE_GENERIC_BAND)
    assert parse("some unrelated apktool chatter") is None


def test_decode_progress_baksmali_band_advances_but_stays_capped():
    parse = _stage_progress_parser(_DECODE_MARKERS, _DECODE_GENERIC_MARKER, _DECODE_GENERIC_BAND)
    parse("I: Decoding values */* XMLs...")  # reach 50 first
    pcts = []
    for i in range(10):
        pct = parse(f"I: Baksmaling classes{i}.dex...")
        if pct is not None:
            pcts.append(pct)
    assert pcts == sorted(pcts)
    assert all(_DECODE_GENERIC_BAND[0] <= p <= _DECODE_GENERIC_BAND[1] for p in pcts)


def test_build_progress_reaches_near_completion_markers():
    parse = _stage_progress_parser(_BUILD_MARKERS, _BUILD_GENERIC_MARKER, _BUILD_GENERIC_BAND)
    log = [
        "I: Using Apktool 2.9.3",
        "I: Checking whether sources has changed...",
        "I: Smaling smali folder into classes.dex...",
        "I: Smaling smali_classes2 folder into classes2.dex...",
        "I: Building resources...",
        "I: Building apk file...",
        "I: Copying unknown files/dir...",
    ]
    seen = [p for p in (parse(line) for line in log) if p is not None]
    assert seen == sorted(seen)
    assert seen[-1] == 95
