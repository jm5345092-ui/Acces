"""ReadOnlyProjectContext — the ONLY door between the assistant and the rest
of the project (architectural review plan, §3).

Every method here returns already-read data (dicts, dataclasses, ORM rows
fetched with plain `db.query(...)` — never `db.add`/`db.commit`). There is
no method here that accepts or returns a writable file handle, a
`ProposedChange`, or anything from `app.core.security.run_tool`.

Allowed imports (enforced by `tests/test_assistant_import_allowlist.py`):
stdlib, `app.core.config`, `app.core.security` (only `resolve_safe_path`,
a validation function), `app.core.db`, the `Project`/`Modification`/`Job`
models (read-only queries), `app.services.manifest_service`,
`app.services.dex_service`, `app.services.smali_read_service`.

Deliberately NOT imported: `app.services.apk_service` (mixes read/write —
see plan §10.3), `app.services.smali_service` (write mutators),
`app.services.comparison_service` (its `.compare()` shells out to
`apksigner` via `signing_service.certificate_info` — see plan §9), and
anything from `build_service`/`signing_service`/`apktool_service`/
`adb_service`/`modification_engine`/`resource_service`.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import resolve_safe_path
from app.models.job import Job
from app.models.modification import Modification
from app.models.project import Project
from app.services import dex_service, manifest_service
from app.services.smali_read_service import class_exists as _class_exists
from app.services.smali_read_service import list_smali_modules as _list_smali_modules

settings = get_settings()

# Statuses where the decoded/ tree is actually complete and safe to analyze.
# `AndroidManifest.xml` alone is NOT a reliable signal: apktool writes it
# early in its extraction and still has smali_classes2/3/... left to write,
# so checking file existence alone produced false-positive "missing class"
# findings against a mid-decode tree (observed live against a real APK: the
# analyzer ran while smali_classes3 was still being extracted and reported
# the launcher Activity as missing, when it was only one module away).
_DECODED_OR_LATER_STATUSES = {
    "DECODED",
    "ANALYZING",
    "ANALYZED",
    "BUILDING",
    "BUILT",
    "SIGNED",
}


class ReadOnlyProjectContext:
    def __init__(self, db: Session, project_id: str) -> None:
        self._db = db
        self.project_id = project_id

    # --- project / workspace paths -----------------------------------
    def get_project(self) -> Project | None:
        return self._db.get(Project, self.project_id)

    def _project_root(self) -> Path:
        # Same primitive `apk_service.project_root()` uses, called directly
        # so this module never has to import the mixed read/write
        # `apk_service` module (plan §10.3).
        return resolve_safe_path(settings.projects_root, self.project_id)

    def decoded_dir(self) -> Path:
        return self._project_root() / "decoded"

    def has_decoded_project(self) -> bool:
        project = self.get_project()
        if not project or project.status not in _DECODED_OR_LATER_STATUSES:
            return False
        return (self.decoded_dir() / "AndroidManifest.xml").exists()

    # --- live, read-only analysis (pure Python/lxml, zero subprocess) ----
    def get_manifest(self) -> dict | None:
        manifest_path = self.decoded_dir() / "AndroidManifest.xml"
        if manifest_path.exists():
            return manifest_service.parse_manifest(manifest_path)
        report = self.get_analysis_report()
        return report.get("manifest") if report else None

    def get_dex_summary(self) -> dict | None:
        if self.has_decoded_project():
            return dex_service.analyze_smali_trees(self.decoded_dir())
        report = self.get_analysis_report()
        return report.get("dex") if report else None

    def get_resources(self) -> dict | None:
        if self.has_decoded_project():
            return dex_service.analyze_resources(self.decoded_dir())
        report = self.get_analysis_report()
        return report.get("resources") if report else None

    def get_assets(self) -> dict | None:
        if self.has_decoded_project():
            return dex_service.analyze_assets(self.decoded_dir())
        report = self.get_analysis_report()
        return report.get("assets") if report else None

    def get_native_libs(self) -> list[str] | None:
        if self.has_decoded_project():
            return dex_service.analyze_native_libs(self.decoded_dir())
        report = self.get_analysis_report()
        return report.get("native_libs") if report else None

    def list_smali_modules(self) -> list[str]:
        if not self.has_decoded_project():
            return []
        return _list_smali_modules(self.decoded_dir())

    def class_exists(self, fqcn: str) -> bool:
        if not self.has_decoded_project():
            return False
        return _class_exists(self.decoded_dir(), fqcn)

    # --- persisted reports (already computed once by the worker) --------
    def get_analysis_report(self) -> dict | None:
        path = self._project_root() / "reports" / "analysis.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def get_comparison_report(self) -> dict | None:
        """Certificate/signature facts live only here — the assistant never
        recomputes them (that would mean calling `comparison_service.compare()`,
        which shells out to `apksigner` under the hood; see plan §9)."""
        path = self._project_root() / "reports" / "comparison.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    # --- history (read-only ORM queries) ---------------------------------
    def list_modifications(self, *, limit: int = 20) -> list[Modification]:
        return (
            self._db.query(Modification)
            .filter(Modification.project_id == self.project_id)
            .order_by(Modification.timestamp.desc())
            .limit(limit)
            .all()
        )

    def list_jobs(self, *, limit: int = 20) -> list[Job]:
        return (
            self._db.query(Job)
            .filter(Job.project_id == self.project_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_last_failed_job(self) -> Job | None:
        from app.models.job import JobStatus

        return (
            self._db.query(Job)
            .filter(Job.project_id == self.project_id, Job.status == JobStatus.FAILED)
            .order_by(Job.created_at.desc())
            .first()
        )

    def get_job_log_tail(self, job_id: str, *, lines: int = 60) -> str:
        log_path = settings.storage_root / "job_logs" / f"{job_id}.log"
        if not log_path.exists():
            return ""
        all_lines = log_path.read_text(errors="ignore").splitlines()
        return "\n".join(all_lines[-lines:])
