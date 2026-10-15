import pytest

from app.core.security import (
    InvalidIdentifierError,
    PathTraversalError,
    ReadOnlyViolationError,
    assert_not_original,
    resolve_safe_path,
    validate_class_name,
    validate_package_name,
)


def test_resolve_safe_path_allows_normal_subpath(tmp_path):
    result = resolve_safe_path(tmp_path, "smali", "com", "example", "Foo.smali")
    assert result == (tmp_path / "smali" / "com" / "example" / "Foo.smali").resolve()


@pytest.mark.parametrize(
    "parts",
    [
        ("..", "etc", "passwd"),
        ("smali", "..", "..", "secret"),
        ("/etc/passwd",),
    ],
)
def test_resolve_safe_path_rejects_traversal(tmp_path, parts):
    with pytest.raises(PathTraversalError):
        resolve_safe_path(tmp_path, *parts)


def test_resolve_safe_path_rejects_absolute_windows_drive(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_safe_path(tmp_path, "C:\\Windows\\System32")


def test_assert_not_original_blocks_write_to_original(tmp_path):
    original = tmp_path / "original" / "original.apk"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"PK")
    with pytest.raises(ReadOnlyViolationError):
        assert_not_original(original, original)


def test_assert_not_original_allows_other_paths(tmp_path):
    original = tmp_path / "original" / "original.apk"
    other = tmp_path / "decoded" / "AndroidManifest.xml"
    assert_not_original(other, original)  # should not raise


def test_validate_package_name_accepts_valid():
    assert validate_package_name("com.example.app") == "com.example.app"


@pytest.mark.parametrize("bad", ["", "com..example", "1com.example", "com/example", "com example"])
def test_validate_package_name_rejects_invalid(bad):
    with pytest.raises(InvalidIdentifierError):
        validate_package_name(bad)


def test_validate_class_name_accepts_valid():
    assert validate_class_name("Logger") == "Logger"


@pytest.mark.parametrize("bad", ["", "1Logger", "Lo gger", "Logger.smali"])
def test_validate_class_name_rejects_invalid(bad):
    with pytest.raises(InvalidIdentifierError):
        validate_class_name(bad)
