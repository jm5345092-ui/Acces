"""GET /api/projects/{id}/jobs/latest?type=X — lets the UI find the right
job to poll for a progress bar regardless of how it navigated to the page
(e.g. decode starts automatically right after upload)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus, JobType
from app.models.project import Project, ProjectStatus


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "latest_job_test.db"
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

    db = session_factory()
    db.add(Project(id="p1", name="demo", status=ProjectStatus.DECODING))
    db.add(Job(id="j1", project_id="p1", type=JobType.DECODE, status=JobStatus.RUNNING, progress=10))
    db.add(Job(id="j2", project_id="p1", type=JobType.DECODE, status=JobStatus.SUCCESS, progress=100))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_returns_the_most_recent_job_of_the_given_type(client):
    resp = client.get("/api/projects/p1/jobs/latest", params={"type": "DECODE"})
    assert resp.status_code == 200
    # j2 was added after j1 within the same test, so it's the most recent.
    assert resp.json()["id"] == "j2"


def test_404_when_no_job_of_that_type_exists(client):
    resp = client.get("/api/projects/p1/jobs/latest", params={"type": "BUILD_PIPELINE"})
    assert resp.status_code == 404


def test_404_for_unknown_project(client):
    resp = client.get("/api/projects/does-not-exist/jobs/latest", params={"type": "DECODE"})
    assert resp.status_code == 404
