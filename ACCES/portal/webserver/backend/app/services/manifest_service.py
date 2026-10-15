"""Parses the decoded (apktool-produced, human-readable XML)
AndroidManifest.xml. Never touches the binary manifest inside the original
APK directly — apktool has already done that translation for us."""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from app.services.change_types import ProposedChange

ANDROID_NS = "http://schemas.android.com/apk/res/android"
NSMAP = {"android": ANDROID_NS}


class ManifestError(Exception):
    pass


def _attr(el, name: str, default: str = "") -> str:
    return el.get(f"{{{ANDROID_NS}}}{name}", default)


def parse_manifest(manifest_path: Path) -> dict:
    tree = etree.parse(str(manifest_path))
    root = tree.getroot()

    uses_sdk = root.find("uses-sdk")
    min_sdk = _attr(uses_sdk, "minSdkVersion") if uses_sdk is not None else ""
    target_sdk = _attr(uses_sdk, "targetSdkVersion") if uses_sdk is not None else ""

    def collect(tag: str) -> list[dict]:
        items = []
        for el in root.iter(tag):
            entry = {"name": _attr(el, "name"), "exported": _attr(el, "exported")}
            if tag == "activity":
                entry["intent_filters"] = _intent_filters(el)
            items.append(entry)
        return items

    permissions = [
        _attr(el, "name") for el in root.findall("uses-permission")
    ]

    application_el = root.find("application")
    application_name = _attr(application_el, "name") if application_el is not None else ""

    return {
        "package": root.get("package", ""),
        "version_code": root.get(f"{{{ANDROID_NS}}}versionCode", ""),
        "version_name": root.get(f"{{{ANDROID_NS}}}versionName", ""),
        "min_sdk": min_sdk,
        "target_sdk": target_sdk,
        "application_name": application_name,
        "activities": collect("activity"),
        "services": collect("service"),
        "receivers": collect("receiver"),
        "providers": collect("provider"),
        "permissions": permissions,
    }


def _intent_filters(activity_el) -> list[dict]:
    filters = []
    for intent_filter in activity_el.findall("intent-filter"):
        actions = [_attr(a, "name") for a in intent_filter.findall("action")]
        categories = [_attr(c, "name") for c in intent_filter.findall("category")]
        filters.append({"actions": actions, "categories": categories})
    return filters


def find_main_activity(manifest_path: Path) -> str | None:
    """Dynamically discovers the launcher Activity — the generic equivalent
    of the "find App.smali" step in the worked example from spec section
    11. Returns the activity's manifest `name` attribute (possibly
    relative, e.g. ".MainActivity"), or None if not found."""
    data = parse_manifest(manifest_path)
    for activity in data["activities"]:
        for intent_filter in activity.get("intent_filters", []):
            if (
                "android.intent.action.MAIN" in intent_filter["actions"]
                and "android.intent.category.LAUNCHER" in intent_filter["categories"]
            ):
                return activity["name"]
    return None


def resolve_activity_class(package: str, activity_name: str) -> str:
    """Resolves a (possibly relative) manifest activity name to a fully
    qualified dotted class name, e.g. package=com.example.app,
    activity_name=".MainActivity" -> com.example.app.MainActivity."""
    if activity_name.startswith("."):
        return f"{package}{activity_name}"
    if "." not in activity_name:
        return f"{package}.{activity_name}"
    return activity_name


def _find_method_line(smali_file: Path, signature_fragment: str) -> int | None:
    """Returns the 1-based line number of the `.method ...` header whose
    signature contains `signature_fragment` (e.g. "onCreate()V"), or None."""
    try:
        lines = smali_file.read_text(errors="ignore").splitlines()
    except OSError:
        return None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(".method") and signature_fragment in stripped:
            return idx + 1
    return None


def find_entry_line(smali_file: Path, *, no_arg_oncreate: bool) -> int:
    """The single most useful line to jump to in a Smali file representing
    an entry point: the body of `onCreate()`, where the app's own code
    actually starts running. Falls back to the constructor, then to the
    top of the file, if `onCreate` isn't overridden there."""
    signature = "onCreate()V" if no_arg_oncreate else "onCreate(Landroid/os/Bundle;)V"
    return (
        _find_method_line(smali_file, signature)
        or _find_method_line(smali_file, "<init>()V")
        or 1
    )


def find_entry_point(manifest_path: Path, decoded_dir: Path) -> dict:
    """What actually runs when the user opens the app, in execution order:
      1. The custom `Application` subclass (if any, declared as
         `android:name` on `<application>`) — its `onCreate()` runs first,
         before any Activity, every time the process starts.
      2. The launcher Activity (MAIN/LAUNCHER intent-filter) — its
         `onCreate()` runs next, when the user actually taps the icon.
    Resolves both to fully-qualified classes and, when the corresponding
    .smali file can be found in the decoded tree, includes its path so the
    UI can link straight to it. Read-only: only uses `manifest_service`
    (pure lxml) and `smali_read_service` (pure file-existence check) —
    never subprocess.
    """
    from app.services.smali_read_service import find_class_file

    data = parse_manifest(manifest_path)
    package = data.get("package", "")
    entry: dict = {
        "application_class": "",
        "application_smali_path": "",
        "application_smali_line": None,
        "main_activity": "",
        "main_activity_class": "",
        "main_activity_smali_path": "",
        "main_activity_smali_line": None,
    }

    app_name = data.get("application_name", "")
    if app_name:
        app_class = resolve_activity_class(package, app_name)
        entry["application_class"] = app_class
        try:
            app_file = find_class_file(decoded_dir, app_class)
            entry["application_smali_path"] = app_file.relative_to(decoded_dir).as_posix()
            entry["application_smali_line"] = find_entry_line(app_file, no_arg_oncreate=True)
        except Exception:
            pass

    main_activity = find_main_activity(manifest_path)
    if main_activity:
        activity_class = resolve_activity_class(package, main_activity)
        entry["main_activity"] = main_activity
        entry["main_activity_class"] = activity_class
        try:
            activity_file = find_class_file(decoded_dir, activity_class)
            entry["main_activity_smali_path"] = activity_file.relative_to(decoded_dir).as_posix()
            entry["main_activity_smali_line"] = find_entry_line(activity_file, no_arg_oncreate=False)
        except Exception:
            pass

    return entry


def propose_modify_manifest(
    manifest_path: Path, xpath: str, attribute: str, value: str
) -> ProposedChange:
    """`xpath` is evaluated with the `android:` namespace bound, e.g.
    ".//application" or ".//activity[@android:name='.MainActivity']".
    `attribute` is the bare (non-namespaced) android: attribute to set."""
    before = manifest_path.read_text()
    tree = etree.fromstring(before.encode())

    matches = tree.xpath(xpath, namespaces=NSMAP)
    if not matches:
        raise ManifestError(f"xpath matched no elements: {xpath}")
    if len(matches) > 1:
        raise ManifestError(f"xpath matched {len(matches)} elements, expected exactly 1: {xpath}")

    target_el = matches[0]
    target_el.set(f"{{{ANDROID_NS}}}{attribute}", value)
    after = etree.tostring(tree, pretty_print=True, encoding="unicode")

    return ProposedChange(
        file="AndroidManifest.xml",
        operation="modify_manifest",
        description=f"Set {attribute}={value!r} on element matching {xpath}",
        before_content=before,
        after_content=after,
    )
