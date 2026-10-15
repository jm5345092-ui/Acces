"""Low-level APK structural inspection shared by the comparison service and
the standalone `tools/apk_validator.py` CLI (spec section 16)."""
from __future__ import annotations

import zipfile
from pathlib import Path

_EXPECTED_PREFIXES = (
    "META-INF/",
    # apktool legitimately renames compiled resource entries on rebuild —
    # e.g. an original `res/-8.xml` (shortened by a third-party resource
    # minifier at the app's original build time) comes back as
    # `res/anim/abc_fade_in.xml` after apktool's own aapt2 recompilation.
    # This is NOT data loss: resource *content* is verified separately by
    # comparing decoded-tree counts in comparison_service (orig vs rebuilt
    # `res/` file counts), which catches real loss without false-flagging
    # every renamed entry. Confirmed against a real production APK where
    # res/ counts matched exactly (740 == 740) despite ~600 renamed zip
    # entries.
    "res/",
)
_EXPECTED_NAMES = {"resources.arsc"}


def _recover_utf8_filename(info: zipfile.ZipInfo) -> str:
    """Python's zipfile decodes a filename as UTF-8 only when the entry's
    UTF-8 flag bit is set, otherwise as CP437 — but many zip writers
    (including apktool's) write UTF-8 bytes without setting that flag,
    which silently mojibakes any non-ASCII filename (e.g. accented
    characters) and makes the *same* file look "removed" from one zip and
    "added" in the other during a set-difference comparison. Recover the
    intended UTF-8 text by re-encoding what Python read as CP437 (lossless,
    since CP437 is a single-byte charset) and decoding that as UTF-8."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return info.filename


def zip_entries(apk_path: Path) -> list[str]:
    with zipfile.ZipFile(apk_path) as zf:
        return [_recover_utf8_filename(info) for info in zf.infolist()]


def is_expected_zip_difference(entry_name: str) -> bool:
    if entry_name in _EXPECTED_NAMES:
        return True
    return any(entry_name.startswith(prefix) for prefix in _EXPECTED_PREFIXES)


def classify_zip_diff(original_apk: Path, rebuilt_apk: Path) -> dict:
    original_entries = set(zip_entries(original_apk))
    rebuilt_entries = set(zip_entries(rebuilt_apk))

    removed = original_entries - rebuilt_entries
    added = rebuilt_entries - original_entries

    expected = [e for e in removed | added if is_expected_zip_difference(e)]
    important = [e for e in removed if not is_expected_zip_difference(e)]
    # New non-META-INF/res files being added is noteworthy but not a "loss"
    # — surfaced separately so it's visible without being flagged as a defect.
    added_notable = [e for e in added if not is_expected_zip_difference(e)]

    return {
        "removed_important": sorted(important),
        "added": sorted(added_notable),
        "expected": sorted(expected),
    }
