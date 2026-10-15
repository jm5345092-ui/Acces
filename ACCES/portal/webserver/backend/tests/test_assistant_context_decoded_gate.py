"""Regression test for a real false positive observed against a live APK:
`has_decoded_project()` used to check only `AndroidManifest.xml` existence,
but apktool writes that file early and still has smali_classes2/3/...
left to extract — so the analyzer briefly saw a "complete-looking" but
actually-partial tree and reported the real launcher Activity as a missing
class. Fixed by gating on the Project's `status` instead of file presence
alone; this test pins that behavior.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.assistant import context as context_module
from app.assistant.context import ReadOnlyProjectContext
from app.core.db import Base
from app.models.project import Project, ProjectStatus


def _make_session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ctx_test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed_decoded_manifest(storage_root, project_id):
    decoded = storage_root / "projects" / project_id / "decoded"
    decoded.mkdir(parents=True)
    (decoded / "AndroidManifest.xml").write_text("<manifest/>")
    (decoded / "smali").mkdir()
    return decoded


def test_has_decoded_project_false_while_status_is_decoding(tmp_path, monkeypatch):
    monkeypatch.setattr(context_module.settings, "storage_root", tmp_path)
    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    project = Project(id="p1", name="demo", status=ProjectStatus.DECODING)
    db.add(project)
    db.commit()

    # Manifest file already exists on disk (apktool wrote it early), but the
    # project row still says DECODING — this must NOT count as "decoded".
    _seed_decoded_manifest(tmp_path, "p1")

    ctx = ReadOnlyProjectContext(db, "p1")
    assert ctx.has_decoded_project() is False
    assert ctx.class_exists("com.example.Anything") is False
    assert ctx.list_smali_modules() == []


def test_has_decoded_project_true_once_status_is_decoded(tmp_path, monkeypatch):
    monkeypatch.setattr(context_module.settings, "storage_root", tmp_path)
    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    project = Project(id="p2", name="demo", status=ProjectStatus.DECODED)
    db.add(project)
    db.commit()

    _seed_decoded_manifest(tmp_path, "p2")

    ctx = ReadOnlyProjectContext(db, "p2")
    assert ctx.has_decoded_project() is True
    assert ctx.list_smali_modules() == ["smali"]
