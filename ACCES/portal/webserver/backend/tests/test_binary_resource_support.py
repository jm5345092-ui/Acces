"""Folder-upload support needs to handle binary files (images, audio) —
these are base64-encoded client-side and round-tripped through
propose -> apply -> revert without corruption."""
from __future__ import annotations

import base64

from app.services import resource_service, smali_service


def test_add_binary_resource_round_trips_through_apply_and_revert(tmp_path):
    decoded_dir = tmp_path / "decoded"
    decoded_dir.mkdir()

    raw_bytes = bytes(range(256))  # exercises every byte value, not just "text-safe" ones
    b64 = base64.b64encode(raw_bytes).decode("ascii")

    change = resource_service.propose_add_resource(
        decoded_dir, "assets/icons/raw.bin", b64, is_binary=True
    )
    assert change.is_binary is True
    assert "binario" in change.diff.lower()

    smali_service.apply_change(decoded_dir, change)
    written = decoded_dir / "assets" / "icons" / "raw.bin"
    assert written.read_bytes() == raw_bytes

    smali_service.revert_change(decoded_dir, change)
    assert not written.exists()


def test_modify_binary_resource_round_trips(tmp_path):
    decoded_dir = tmp_path / "decoded"
    (decoded_dir / "res" / "raw").mkdir(parents=True)
    original_bytes = b"\x89PNG\r\n\x1a\nORIGINAL"
    target = decoded_dir / "res" / "raw" / "icon.png"
    target.write_bytes(original_bytes)

    new_bytes = b"\x89PNG\r\n\x1a\nREPLACED"
    change = resource_service.propose_modify_resource(
        decoded_dir, "res/raw/icon.png", base64.b64encode(new_bytes).decode("ascii"), is_binary=True
    )
    assert base64.b64decode(change.before_content) == original_bytes

    smali_service.apply_change(decoded_dir, change)
    assert target.read_bytes() == new_bytes

    smali_service.revert_change(decoded_dir, change)
    assert target.read_bytes() == original_bytes


def test_text_resource_default_is_not_binary(tmp_path):
    decoded_dir = tmp_path / "decoded"
    decoded_dir.mkdir()
    change = resource_service.propose_add_resource(decoded_dir, "assets/notes.txt", "hello")
    assert change.is_binary is False
    smali_service.apply_change(decoded_dir, change)
    assert (decoded_dir / "assets" / "notes.txt").read_text() == "hello"
