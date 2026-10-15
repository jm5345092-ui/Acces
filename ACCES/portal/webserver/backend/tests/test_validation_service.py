import zipfile

from app.services import validation_service


def make_zip(path, entries: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_expected_vs_important_classification(tmp_path):
    original = make_zip(
        tmp_path / "original.apk",
        {
            "AndroidManifest.xml": b"...",
            "classes.dex": b"...",
            "assets/notes.txt": b"hello",
            "META-INF/CERT.SF": b"...",
            "resources.arsc": b"...",
        },
    )
    rebuilt = make_zip(
        tmp_path / "rebuilt.apk",
        {
            "AndroidManifest.xml": b"...",
            "classes.dex": b"...",
            # assets/notes.txt intentionally dropped -> IMPORTANT
            "META-INF/CERT.SF": b"different-signature-bytes",  # expected
            "resources.arsc": b"different-bytes",  # expected
        },
    )

    diff = validation_service.classify_zip_diff(original, rebuilt)
    assert "assets/notes.txt" in diff["removed_important"]
    assert "META-INF/CERT.SF" not in diff["removed_important"]
    assert "resources.arsc" not in diff["removed_important"]


def test_no_differences_when_identical(tmp_path):
    original = make_zip(tmp_path / "original.apk", {"a.txt": b"x"})
    rebuilt = make_zip(tmp_path / "rebuilt.apk", {"a.txt": b"x"})
    diff = validation_service.classify_zip_diff(original, rebuilt)
    assert diff["removed_important"] == []
    assert diff["added"] == []


def test_is_expected_zip_difference():
    assert validation_service.is_expected_zip_difference("META-INF/MANIFEST.MF")
    assert validation_service.is_expected_zip_difference("resources.arsc")
    assert not validation_service.is_expected_zip_difference("assets/data.bin")


def test_renamed_resource_entries_are_expected_not_important(tmp_path):
    """Regression test from a real production APK (Pou): apktool rebuilds
    resources with readable aapt2 names (res/anim/abc_fade_in.xml) even
    when the original app's build pipeline had shortened them to
    res/-8.xml via a third-party resource minifier. 600+ renamed entries
    must not be reported as data loss when the resource count matches."""
    original = make_zip(tmp_path / "original.apk", {"res/-8.xml": b"<anim/>"})
    rebuilt = make_zip(tmp_path / "rebuilt.apk", {"res/anim/abc_fade_in.xml": b"<anim/>"})

    diff = validation_service.classify_zip_diff(original, rebuilt)
    assert diff["removed_important"] == []
    assert "res/-8.xml" in diff["expected"]


def test_recover_utf8_filename_when_utf8_flag_not_set():
    """Regression test: apktool's zip writer doesn't always set the UTF-8
    flag bit even when it writes UTF-8 filename bytes, which made Python's
    zipfile mis-decode accented filenames as CP437 — the same physical
    file then looked "removed" (original, correctly UTF-8-flagged) and
    "added" (rebuilt, mis-decoded) instead of unchanged."""
    info = zipfile.ZipInfo("placeholder")
    info.filename = "assets/images/Atlético Madrid.png".encode("utf-8").decode("cp437")
    info.flag_bits = 0  # UTF-8 flag intentionally NOT set, as apktool's writer does

    recovered = validation_service._recover_utf8_filename(info)
    assert recovered == "assets/images/Atlético Madrid.png"


def test_recover_utf8_filename_passthrough_when_flag_set():
    info = zipfile.ZipInfo("assets/images/Atlético Madrid.png")
    info.flag_bits = 0x800  # UTF-8 flag set — already decoded correctly by zipfile
    assert validation_service._recover_utf8_filename(info) == "assets/images/Atlético Madrid.png"
