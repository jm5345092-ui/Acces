from app.services import manifest_service

MANIFEST_XML = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.app"
    android:versionCode="7"
    android:versionName="1.2.3">

    <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="34" />

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.CAMERA" />

    <application android:label="Example" android:name=".MyApp">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
        <activity android:name=".SettingsActivity" android:exported="false" />
        <service android:name=".SyncService" android:exported="false" />
        <receiver android:name=".BootReceiver" android:exported="true" />
    </application>
</manifest>
"""

MANIFEST_XML_NO_APPLICATION_NAME = MANIFEST_XML.replace(' android:name=".MyApp"', "")


def write_manifest(tmp_path):
    path = tmp_path / "AndroidManifest.xml"
    path.write_text(MANIFEST_XML)
    return path


def test_parse_manifest_basic_fields(tmp_path):
    data = manifest_service.parse_manifest(write_manifest(tmp_path))
    assert data["package"] == "com.example.app"
    assert data["version_code"] == "7"
    assert data["version_name"] == "1.2.3"
    assert data["min_sdk"] == "21"
    assert data["target_sdk"] == "34"
    assert "android.permission.INTERNET" in data["permissions"]
    assert "android.permission.CAMERA" in data["permissions"]
    assert len(data["activities"]) == 2
    assert len(data["services"]) == 1
    assert len(data["receivers"]) == 1


def test_find_main_activity_discovers_launcher_dynamically(tmp_path):
    main_activity = manifest_service.find_main_activity(write_manifest(tmp_path))
    assert main_activity == ".MainActivity"


def test_resolve_activity_class_handles_relative_name():
    assert (
        manifest_service.resolve_activity_class("com.example.app", ".MainActivity")
        == "com.example.app.MainActivity"
    )


def test_resolve_activity_class_handles_fully_qualified_name():
    assert (
        manifest_service.resolve_activity_class("com.example.app", "com.example.app.MainActivity")
        == "com.example.app.MainActivity"
    )


def test_propose_modify_manifest_sets_attribute(tmp_path):
    manifest_path = write_manifest(tmp_path)
    change = manifest_service.propose_modify_manifest(
        manifest_path,
        xpath=".//activity[@android:name='.SettingsActivity']",
        attribute="exported",
        value="true",
    )
    assert 'android:exported="true"' in change.after_content
    assert change.file == "AndroidManifest.xml"


def test_find_entry_point_resolves_application_and_main_activity_with_smali_paths(tmp_path):
    manifest_path = write_manifest(tmp_path)
    smali_dir = tmp_path / "smali" / "com" / "example" / "app"
    smali_dir.mkdir(parents=True)
    (smali_dir / "MyApp.smali").write_text(".class public Lcom/example/app/MyApp;\n")
    (smali_dir / "MainActivity.smali").write_text(".class public Lcom/example/app/MainActivity;\n")

    entry = manifest_service.find_entry_point(manifest_path, tmp_path)
    assert entry["application_class"] == "com.example.app.MyApp"
    assert entry["application_smali_path"] == "smali/com/example/app/MyApp.smali"
    assert entry["application_smali_line"] == 1  # no onCreate/<init> in this trivial fixture — falls back to line 1
    assert entry["main_activity"] == ".MainActivity"
    assert entry["main_activity_class"] == "com.example.app.MainActivity"
    assert entry["main_activity_smali_path"] == "smali/com/example/app/MainActivity.smali"
    assert entry["main_activity_smali_line"] == 1


def test_find_entry_point_jumps_to_oncreate_line_when_present(tmp_path):
    manifest_path = write_manifest(tmp_path)
    smali_dir = tmp_path / "smali" / "com" / "example" / "app"
    smali_dir.mkdir(parents=True)
    (smali_dir / "MyApp.smali").write_text(
        ".class public Lcom/example/app/MyApp;\n"
        ".super Landroid/app/Application;\n\n"
        ".method public constructor <init>()V\n"
        "    .locals 0\n"
        "    return-void\n"
        ".end method\n\n"
        ".method public onCreate()V\n"
        "    .locals 0\n"
        "    return-void\n"
        ".end method\n"
    )
    (smali_dir / "MainActivity.smali").write_text(
        ".class public Lcom/example/app/MainActivity;\n"
        ".super Landroid/app/Activity;\n\n"
        ".method protected onCreate(Landroid/os/Bundle;)V\n"
        "    .locals 0\n"
        "    return-void\n"
        ".end method\n"
    )

    entry = manifest_service.find_entry_point(manifest_path, tmp_path)
    assert entry["application_smali_line"] == 9  # ".method public onCreate()V"
    assert entry["main_activity_smali_line"] == 4  # ".method protected onCreate(Landroid/os/Bundle;)V"


def test_find_entry_point_falls_back_to_constructor_when_no_oncreate(tmp_path):
    manifest_path = write_manifest(tmp_path)
    smali_dir = tmp_path / "smali" / "com" / "example" / "app"
    smali_dir.mkdir(parents=True)
    (smali_dir / "MainActivity.smali").write_text(
        ".class public Lcom/example/app/MainActivity;\n"
        ".super Landroid/app/Activity;\n\n"
        ".method public constructor <init>()V\n"
        "    .locals 0\n"
        "    return-void\n"
        ".end method\n"
    )

    entry = manifest_service.find_entry_point(manifest_path, tmp_path)
    assert entry["main_activity_smali_line"] == 4


def test_find_entry_point_handles_missing_smali_files_gracefully(tmp_path):
    manifest_path = write_manifest(tmp_path)
    # No smali/ tree at all — classes can't be located, but this must not raise.
    entry = manifest_service.find_entry_point(manifest_path, tmp_path)
    assert entry["application_class"] == "com.example.app.MyApp"
    assert entry["application_smali_path"] == ""
    assert entry["main_activity_class"] == "com.example.app.MainActivity"
    assert entry["main_activity_smali_path"] == ""


def test_find_entry_point_without_custom_application_class(tmp_path):
    manifest_path = tmp_path / "AndroidManifest.xml"
    manifest_path.write_text(MANIFEST_XML_NO_APPLICATION_NAME)
    entry = manifest_service.find_entry_point(manifest_path, tmp_path)
    assert entry["application_class"] == ""
    assert entry["application_smali_path"] == ""
    assert entry["main_activity_class"] == "com.example.app.MainActivity"


def test_propose_modify_manifest_raises_on_no_match(tmp_path):
    manifest_path = write_manifest(tmp_path)
    try:
        manifest_service.propose_modify_manifest(
            manifest_path,
            xpath=".//activity[@android:name='.DoesNotExist']",
            attribute="exported",
            value="true",
        )
        assert False, "expected ManifestError"
    except manifest_service.ManifestError:
        pass
