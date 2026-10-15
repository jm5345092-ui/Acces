"""Plan §14 test: ProjectAnalyzer, fully deterministic, no LLM, no DB, no
filesystem — driven through a fake duck-typed ReadOnlyProjectContext so the
analyzer's branching logic is tested in isolation."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.assistant.analyzer import ProjectAnalyzer
from app.models.assistant import AssistantConfidence

MANIFEST_WITH_ACTIVITY = {
    "package": "com.example.app",
    "activities": [{"name": ".MainActivity", "exported": "true", "intent_filters": []}],
    "services": [],
    "receivers": [],
    "providers": [],
}


class FakeContext:
    def __init__(
        self,
        *,
        manifest=None,
        decoded=True,
        existing_classes=(),
        smali_modules=("smali",),
        last_failed_job=None,
        job_log_tail="",
        modifications=(),
        comparison_report=None,
    ):
        self._manifest = manifest
        self._decoded = decoded
        self._existing_classes = set(existing_classes)
        self._smali_modules = list(smali_modules)
        self._last_failed_job = last_failed_job
        self._job_log_tail = job_log_tail
        self._modifications = list(modifications)
        self._comparison_report = comparison_report

    def get_manifest(self):
        return self._manifest

    def has_decoded_project(self):
        return self._decoded

    def list_smali_modules(self):
        return self._smali_modules

    def class_exists(self, fqcn):
        return fqcn in self._existing_classes

    def get_last_failed_job(self):
        return self._last_failed_job

    def get_job_log_tail(self, job_id, lines=60):
        return self._job_log_tail

    def list_modifications(self, limit=20):
        return self._modifications

    def get_comparison_report(self):
        return self._comparison_report


def test_missing_manifest_class_yields_hypothesis_finding():
    ctx = FakeContext(manifest=MANIFEST_WITH_ACTIVITY, existing_classes=())
    findings = ProjectAnalyzer(ctx).analyze()

    class_findings = [f for f in findings if "MainActivity" in f.observation]
    assert len(class_findings) == 1
    finding = class_findings[0]
    assert finding.confidence == AssistantConfidence.HYPOTHESIS.value
    assert "com.example.app.MainActivity" in finding.evidence
    # must list possibilities, never assert a confirmed error
    assert "no se encontró" not in finding.observation.lower() or "declara" in finding.observation.lower()
    assert "clase todavía no existe" in finding.possible_problem.lower() or "no coincide" in finding.possible_problem.lower()


def test_present_manifest_class_yields_no_finding():
    ctx = FakeContext(
        manifest=MANIFEST_WITH_ACTIVITY,
        existing_classes={"com.example.app.MainActivity"},
    )
    findings = ProjectAnalyzer(ctx).analyze()
    assert findings == []


def test_no_decoded_project_yields_no_manifest_findings():
    ctx = FakeContext(manifest=MANIFEST_WITH_ACTIVITY, decoded=False)
    findings = ProjectAnalyzer(ctx).analyze()
    assert findings == []


def test_failed_job_yields_confirmed_fact_finding_with_related_hypothesis():
    mod_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    job_time = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)  # job created after the modification
    failed_job = SimpleNamespace(id="job123", type="BUILD_PIPELINE", created_at=job_time)
    applied_mod = SimpleNamespace(id="mod1", status="APPLIED", timestamp=mod_time)
    ctx = FakeContext(
        manifest=None,
        decoded=False,
        last_failed_job=failed_job,
        job_log_tail="apktool: error parsing resource",
        modifications=[applied_mod],
    )
    findings = ProjectAnalyzer(ctx).analyze()

    assert len(findings) == 1
    finding = findings[0]
    assert finding.confidence == AssistantConfidence.CONFIRMED_FACT.value
    assert "job123" in finding.evidence
    assert finding.related_modification_ids == ["mod1"]
    # causality must be phrased as a possibility, never an assertion
    assert "causó" not in finding.suggestion.lower()
    assert "podría estar relacionada" in finding.suggestion.lower()


def test_comparison_warning_only_surfaces_when_incompatible():
    ctx_ok = FakeContext(comparison_report={"compatible": True, "important_differences": []})
    assert ProjectAnalyzer(ctx_ok).analyze() == []

    ctx_bad = FakeContext(
        comparison_report={"compatible": False, "important_differences": ["Class count decreased"]}
    )
    findings = ProjectAnalyzer(ctx_bad).analyze()
    assert len(findings) == 1
    assert findings[0].confidence == AssistantConfidence.CONFIRMED_FACT.value
