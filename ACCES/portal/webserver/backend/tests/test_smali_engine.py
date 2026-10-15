import pytest

from app.services import smali_service
from app.services.smali_service import ModificationError

MAIN_ACTIVITY_SMALI = """.class public Lcom/example/app/MainActivity;
.super Landroid/app/Activity;

.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    return-void
.end method

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 1

    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    return-void
.end method
"""


@pytest.fixture
def decoded_dir(tmp_path):
    root = tmp_path / "decoded"
    activity_path = root / "smali" / "com" / "example" / "app" / "MainActivity.smali"
    activity_path.parent.mkdir(parents=True)
    activity_path.write_text(MAIN_ACTIVITY_SMALI)
    return root


def test_create_smali_package(decoded_dir):
    change = smali_service.propose_create_smali_package(decoded_dir, "me.pou.app.prueba")
    assert change.operation == "create_smali_package"
    assert not (decoded_dir / "smali" / "me" / "pou" / "app" / "prueba").exists()
    smali_service.apply_change(decoded_dir, change)
    assert (decoded_dir / "smali" / "me" / "pou" / "app" / "prueba").exists()


def test_create_smali_class_generates_valid_skeleton(decoded_dir):
    change = smali_service.propose_create_smali_class(decoded_dir, "me.pou.app.prueba", "Prueba")
    assert ".class public final Lme/pou/app/prueba/Prueba;" in change.after_content
    assert ".super Ljava/lang/Object;" in change.after_content
    assert not (decoded_dir / "smali" / "me" / "pou" / "app" / "prueba" / "Prueba.smali").exists()

    smali_service.apply_change(decoded_dir, change)
    written = decoded_dir / "smali" / "me" / "pou" / "app" / "prueba" / "Prueba.smali"
    assert written.exists()
    assert written.read_text() == change.after_content


def test_create_smali_class_rejects_duplicate(decoded_dir):
    change = smali_service.propose_create_smali_class(decoded_dir, "me.pou.app.prueba", "Prueba")
    smali_service.apply_change(decoded_dir, change)
    with pytest.raises(ModificationError):
        smali_service.propose_create_smali_class(decoded_dir, "me.pou.app.prueba", "Prueba")


def test_find_class_file_locates_dynamically(decoded_dir):
    found = smali_service.find_class_file(decoded_dir, "com.example.app.MainActivity")
    assert found == decoded_dir / "smali" / "com" / "example" / "app" / "MainActivity.smali"


def test_insert_smali_instruction_into_oncreate(decoded_dir):
    change = smali_service.propose_insert_smali_instruction(
        decoded_dir,
        "com.example.app.MainActivity",
        "onCreate(Landroid/os/Bundle;)V",
        "invoke-static {}, Lme/pou/app/prueba/Prueba;->ejecutar()V",
        position="start",
    )
    assert "invoke-static {}, Lme/pou/app/prueba/Prueba;->ejecutar()V" in change.after_content
    # must land inside onCreate, after its .locals header, not before it
    before_oncreate, _, after_oncreate = change.after_content.partition("onCreate")
    assert "invoke-static" not in before_oncreate

    smali_service.apply_change(decoded_dir, change)
    written = decoded_dir / "smali" / "com" / "example" / "app" / "MainActivity.smali"
    assert "invoke-static {}, Lme/pou/app/prueba/Prueba;->ejecutar()V" in written.read_text()


def test_insert_smali_instruction_missing_method_raises(decoded_dir):
    with pytest.raises(ModificationError):
        smali_service.propose_insert_smali_instruction(
            decoded_dir,
            "com.example.app.MainActivity",
            "onDestroy()V",
            "return-void",
        )


def test_apply_then_revert_restores_original(decoded_dir):
    activity_file = decoded_dir / "smali" / "com" / "example" / "app" / "MainActivity.smali"
    original_text = activity_file.read_text()

    change = smali_service.propose_insert_smali_instruction(
        decoded_dir,
        "com.example.app.MainActivity",
        "onCreate(Landroid/os/Bundle;)V",
        "invoke-static {}, Lme/pou/app/prueba/Prueba;->ejecutar()V",
    )
    smali_service.apply_change(decoded_dir, change)
    assert activity_file.read_text() != original_text

    smali_service.revert_change(decoded_dir, change)
    assert activity_file.read_text() == original_text


def test_create_class_revert_deletes_file(decoded_dir):
    change = smali_service.propose_create_smali_class(decoded_dir, "me.pou.app.prueba", "Prueba")
    smali_service.apply_change(decoded_dir, change)
    written = decoded_dir / "smali" / "me" / "pou" / "app" / "prueba" / "Prueba.smali"
    assert written.exists()

    smali_service.revert_change(decoded_dir, change)
    assert not written.exists()


def test_package_discovery_is_not_hardcoded(decoded_dir):
    """Guards against regressing into the spec's explicit anti-pattern:
    nothing about 'me.pou.app' or 'smali_classes3' may be hardcoded — the
    engine must work for an arbitrary package/module requested at call time."""
    change = smali_service.propose_create_smali_class(decoded_dir, "org.other.thing", "Widget")
    assert "Lorg/other/thing/Widget;" in change.after_content
