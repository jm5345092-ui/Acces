"""Plan §14 test I: POST /assistant/ask may only ever write AssistantMessage
/AssistantEvent rows — Project/Modification/Job must be byte-for-byte
unchanged after the call. Uses an isolated temp-file SQLite DB (via a
FastAPI dependency override), never the real storage/DB used by other
tests or the running app."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.assistant.provider import AssistantAnswer
from app.core.db import Base, get_db
from app.main import app
from app.models.assistant import AssistantEvent, AssistantMessage  # noqa: F401 (registers tables)
from app.models.job import Job, JobStatus, JobType
from app.models.modification import Modification, ModificationStatus
from app.models.project import Project, ProjectStatus


class _StubProvider:
    def answer(self, *, project_context, history, question):
        return AssistantAnswer(message="respuesta de prueba (stub, sin red)", mode="general")


@pytest.fixture
def isolated_session_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "assistant_write_scope_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.assistant.service.get_assistant_provider", lambda name: _StubProvider())
    yield session_factory
    app.dependency_overrides.clear()


def _row_snapshot(obj, fields):
    return tuple(getattr(obj, f) for f in fields)


def test_ask_only_writes_assistant_message_and_event_rows(isolated_session_factory):
    db = isolated_session_factory()
    project = Project(id="proj1", name="demo", status=ProjectStatus.CREATED)
    mod = Modification(
        id="mod1",
        project_id="proj1",
        file="AndroidManifest.xml",
        operation="modify_manifest",
        description="test mod",
        status=ModificationStatus.APPLIED,
    )
    job = Job(id="job1", project_id="proj1", type=JobType.BUILD_PIPELINE, status=JobStatus.FAILED)
    db.add_all([project, mod, job])
    db.commit()

    project_fields = ("id", "name", "status", "package_name", "sha256")
    mod_fields = ("id", "operation", "status", "before_content", "after_content", "file")
    job_fields = ("id", "type", "status", "result_json", "progress")

    before_project = _row_snapshot(project, project_fields)
    before_mod = _row_snapshot(mod, mod_fields)
    before_job = _row_snapshot(job, job_fields)
    db.close()

    with TestClient(app) as client:
        resp = client.post("/api/projects/proj1/assistant/ask", json={"question": "¿qué pasó con el build?"})
    assert resp.status_code == 200, resp.text

    db2 = isolated_session_factory()
    after_project = _row_snapshot(db2.get(Project, "proj1"), project_fields)
    after_mod = _row_snapshot(db2.get(Modification, "mod1"), mod_fields)
    after_job = _row_snapshot(db2.get(Job, "job1"), job_fields)

    assert after_project == before_project
    assert after_mod == before_mod
    assert after_job == before_job

    messages = db2.query(AssistantMessage).filter(AssistantMessage.project_id == "proj1").all()
    assert len(messages) == 2  # user question + assistant answer
    assert {m.role for m in messages} == {"user", "assistant"}

    events = db2.query(AssistantEvent).filter(AssistantEvent.project_id == "proj1").all()
    assert len(events) >= 1  # at least the failed-job finding gets logged
    assert all(e.project_id == "proj1" for e in events)
    db2.close()
