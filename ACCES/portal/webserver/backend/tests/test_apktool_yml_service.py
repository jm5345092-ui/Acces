"""Regression test: a real production APK decoded during manual testing had
blank min_sdk/target_sdk/version_code/version_name in the analysis report
because apktool moved that info into apktool.yml instead of keeping a
<uses-sdk> element in AndroidManifest.xml."""
from __future__ import annotations

from app.services import apktool_yml_service

SAMPLE_YML = """\
version: 2.9.3
apkFileName: original.apk
isFrameworkApk: false
sdkInfo:
  minSdkVersion: 26
  targetSdkVersion: 37
packageInfo:
  forcedPackageId: 127
versionInfo:
  versionCode: 1
  versionName: 0.1.0
resourcesAreCompressed: false
"""


def test_parse_apktool_yml_extracts_sdk_and_version_info(tmp_path):
    (tmp_path / "apktool.yml").write_text(SAMPLE_YML)
    data = apktool_yml_service.parse_apktool_yml(tmp_path)
    assert data["min_sdk"] == "26"
    assert data["target_sdk"] == "37"
    assert data["version_code"] == "1"
    assert data["version_name"] == "0.1.0"
    assert data["apktool_version"] == "2.9.3"


def test_parse_apktool_yml_missing_file_returns_empty_dict(tmp_path):
    assert apktool_yml_service.parse_apktool_yml(tmp_path) == {}


def test_enrich_prefers_manifest_values_when_present(tmp_path):
    (tmp_path / "apktool.yml").write_text(SAMPLE_YML)
    manifest = {"min_sdk": "21", "target_sdk": "", "version_code": "", "version_name": ""}
    enriched = apktool_yml_service.enrich_manifest_with_apktool_yml(manifest, tmp_path)
    assert enriched["min_sdk"] == "21"  # manifest's own value wins, not overwritten
    assert enriched["target_sdk"] == "37"  # blank in manifest -> filled from apktool.yml
    assert enriched["version_code"] == "1"
    assert enriched["version_name"] == "0.1.0"
    assert enriched["compile_sdk"] == ""
    assert enriched["apktool_version"] == "2.9.3"


def test_enrich_handles_missing_apktool_yml_gracefully(tmp_path):
    manifest = {"min_sdk": "", "target_sdk": ""}
    enriched = apktool_yml_service.enrich_manifest_with_apktool_yml(manifest, tmp_path)
    assert enriched["min_sdk"] == ""
    assert enriched["target_sdk"] == ""
    assert enriched["apktool_version"] == ""
