"""DEX/class/method statistics derived from the decoded Smali tree.

Deliberately avoids a binary DEX parser dependency: after `apktool d`,
every class and method already exists as a `.class`/`.method` declaration
line in the smali*/ directories, so counting those is accurate and much
simpler than re-parsing classes.dex ourselves.
"""
from __future__ import annotations

import re
from pathlib import Path

_CLASS_RE = re.compile(r"^\.class\s", re.MULTILINE)
_METHOD_RE = re.compile(r"^\.method\s", re.MULTILINE)


def analyze_smali_trees(decoded_dir: Path) -> dict:
    per_dex: dict[str, dict] = {}
    total_classes = 0
    total_methods = 0
    packages: set[str] = set()

    for smali_dir in sorted(decoded_dir.glob("smali*")):
        if not smali_dir.is_dir():
            continue
        classes = 0
        methods = 0
        for smali_file in smali_dir.rglob("*.smali"):
            text = smali_file.read_text(errors="ignore")
            classes += len(_CLASS_RE.findall(text))
            methods += len(_METHOD_RE.findall(text))
            rel_pkg = smali_file.relative_to(smali_dir).parent.as_posix().replace("/", ".")
            if rel_pkg and rel_pkg != ".":
                packages.add(rel_pkg)
        per_dex[smali_dir.name] = {"classes": classes, "methods": methods}
        total_classes += classes
        total_methods += methods

    return {
        "per_dex": per_dex,
        "total_classes": total_classes,
        "total_methods": total_methods,
        "packages": sorted(packages),
        "package_count": len(packages),
    }


def analyze_native_libs(decoded_dir: Path) -> list[str]:
    lib_dir = decoded_dir / "lib"
    if not lib_dir.exists():
        return []
    return sorted(str(p.relative_to(decoded_dir)) for p in lib_dir.rglob("*.so"))


def analyze_assets(decoded_dir: Path) -> dict:
    assets_dir = decoded_dir / "assets"
    if not assets_dir.exists():
        return {"count": 0, "files": []}
    files = sorted(str(p.relative_to(assets_dir)) for p in assets_dir.rglob("*") if p.is_file())
    return {"count": len(files), "files": files}


def analyze_resources(decoded_dir: Path) -> dict:
    res_dir = decoded_dir / "res"
    if not res_dir.exists():
        return {"count": 0, "by_type": {}}
    by_type: dict[str, int] = {}
    total = 0
    for p in res_dir.rglob("*"):
        if p.is_file():
            total += 1
            type_dir = p.parent.name.split("-")[0]
            by_type[type_dir] = by_type.get(type_dir, 0) + 1
    return {"count": total, "by_type": by_type}
