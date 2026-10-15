#!/usr/bin/env python3
"""Standalone CLI validator (spec section 16):

    python3 tools/apk_validator.py original.apk rebuilt.apk --compare

Decodes both APKs with apktool into temporary directories and reports
EXPECTED vs IMPORTANT differences, independent of the web platform (useful
in CI or a terminal on the worker host). Requires apktool/java/aapt2/
apksigner on PATH — i.e. run this inside the worker container or an
equivalent environment, never on arbitrary/untrusted input outside a
sandbox.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services import apktool_service, comparison_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("rebuilt", type=Path)
    parser.add_argument("--compare", action="store_true", help="(implied) run the comparison")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a summary")
    args = parser.parse_args()

    for path in (args.original, args.rebuilt):
        if not path.exists():
            print(f"error: file not found: {path}", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="apklab-validate-") as tmp:
        tmp_path = Path(tmp)
        original_decoded = tmp_path / "original_decoded"
        rebuilt_decoded = tmp_path / "rebuilt_decoded"

        for apk, out in ((args.original, original_decoded), (args.rebuilt, rebuilt_decoded)):
            result = apktool_service.decode(apk, out)
            if result.returncode != 0:
                print(f"error: apktool decode failed for {apk}:\n{result.stderr}", file=sys.stderr)
                return 1

        report = comparison_service.compare(
            original_apk=args.original,
            rebuilt_apk=args.rebuilt,
            original_decoded=original_decoded,
            rebuilt_decoded=rebuilt_decoded,
        )

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["compatible"] else 1

    print("ORIGINAL vs MODIFICADO\n")
    for key, values in report["summary"].items():
        print(f"{key}: {values}")
    print()
    if report["expected_differences"]:
        print("DIFERENCIAS ESPERADAS:")
        for item in report["expected_differences"]:
            print(f"  - {item}")
        print()
    if report["important_differences"]:
        print("DIFERENCIAS IMPORTANTES:")
        for item in report["important_differences"]:
            print(f"  ! {item}")
        print()

    if report["compatible"]:
        print("MODIFICACIÓN COMPATIBLE — sin pérdidas detectadas")
        return 0
    print("MODIFICACIÓN CON DIFERENCIAS IMPORTANTES")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
