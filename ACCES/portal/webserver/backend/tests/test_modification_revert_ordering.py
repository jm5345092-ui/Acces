"""Reverting a Modification must only ever undo that specific change —
never silently discard a later change applied on top of the same file.
Since revert works by writing `before_content` over the whole file, the
only safe way to guarantee that without a real patch/merge engine is to
require same-file reverts to happen in last-applied-first order."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base, get_db
from app.main import app
from app.models.project import Project, ProjectStatus
from app.services import apk_service


@pytest.fixture
def client_with_decoded_project(tmp_path, monkeypatch):
    db_path = tmp_path / "revert_order_test.db"
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

    # Point storage at an isolated tmp dir and seed a minimal decoded project.
    monkeypatch.setattr(apk_service.settings, "storage_root", tmp_path / "storage")
    project_id = "projA"
    decoded_dir = apk_service.project_root(project_id) / "decoded"
    decoded_dir.mkdir(parents=True)
    (decoded_dir / "AndroidManifest.xml").write_text("<manifest/>")

    db = session_factory()
    db.add(Project(id=project_id, name="test", status=ProjectStatus.DECODED))
    db.commit()
    db.close()

    with TestClient(app) as client:
        yield client, project_id

    app.dependency_overrides.clear()


def _propose_and_apply(client: TestClient, project_id: str, path: str, content: str) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/modifications",
        json={"operation": "add_resource", "path": path, "content": content},
    )
    assert resp.status_code == 200, resp.text
    mod = resp.json()
    resp2 = client.post(f"/api/projects/{project_id}/modifications/{mod['id']}/apply")
    assert resp2.status_code == 200, resp2.text
    return resp2.json()


def _propose_and_apply_modify(client: TestClient, project_id: str, path: str, content: str) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/modifications",
        json={"operation": "modify_resource", "path": path, "content": content},
    )
    assert resp.status_code == 200, resp.text
    mod = resp.json()
    resp2 = client.post(f"/api/projects/{project_id}/modifications/{mod['id']}/apply")
    assert resp2.status_code == 200, resp2.text
    return resp2.json()


def test_reverting_middle_change_on_same_file_is_blocked(client_with_decoded_project):
    client, project_id = client_with_decoded_project

    mod1 = _propose_and_apply(client, project_id, "assets/notes.txt", "v1")
    mod2 = _propose_and_apply_modify(client, project_id, "assets/notes.txt", "v2")
    mod3 = _propose_and_apply_modify(client, project_id, "assets/notes.txt", "v3")

    # Reverting mod1 (the first/oldest) must be blocked — mod2 and mod3 are
    # later APPLIED changes on the exact same file.
    resp = client.post(f"/api/projects/{project_id}/modifications/{mod1['id']}/revert")
    assert resp.status_code == 409
    assert mod2["id"] in resp.json()["detail"] or "más reciente" in resp.json()["detail"]

    # Reverting mod2 is also blocked — mod3 is still later and still applied.
    resp2 = client.post(f"/api/projects/{project_id}/modifications/{mod2['id']}/revert")
    assert resp2.status_code == 409

    # The file content must be untouched by the blocked attempts.
    read = client.get(f"/api/projects/{project_id}/file", params={"path": "notes.txt", "subdir": "decoded/assets"})
    assert read.json()["content"] == "v3"


def test_reverting_in_last_applied_first_order_succeeds(client_with_decoded_project):
    client, project_id = client_with_decoded_project

    mod1 = _propose_and_apply(client, project_id, "assets/notes.txt", "v1")
    mod2 = _propose_and_apply_modify(client, project_id, "assets/notes.txt", "v2")
    mod3 = _propose_and_apply_modify(client, project_id, "assets/notes.txt", "v3")

    # Revert the LAST one first — allowed, restores v2.
    resp3 = client.post(f"/api/projects/{project_id}/modifications/{mod3['id']}/revert")
    assert resp3.status_code == 200, resp3.text
    read = client.get(f"/api/projects/{project_id}/file", params={"path": "notes.txt", "subdir": "decoded/assets"})
    assert read.json()["content"] == "v2"

    # Now mod2 is the latest APPLIED on that file — allowed, restores v1.
    resp2 = client.post(f"/api/projects/{project_id}/modifications/{mod2['id']}/revert")
    assert resp2.status_code == 200, resp2.text
    read2 = client.get(f"/api/projects/{project_id}/file", params={"path": "notes.txt", "subdir": "decoded/assets"})
    assert read2.json()["content"] == "v1"

    # Finally mod1 — allowed, file goes back to not existing (it was a
    # create via add_resource).
    resp1 = client.post(f"/api/projects/{project_id}/modifications/{mod1['id']}/revert")
    assert resp1.status_code == 200, resp1.text


def test_reverting_changes_on_different_files_is_never_blocked(client_with_decoded_project):
    client, project_id = client_with_decoded_project

    mod1 = _propose_and_apply(client, project_id, "assets/a.txt", "a")
    _propose_and_apply(client, project_id, "assets/b.txt", "b")

    # mod1 touches a different file than the later change — reverting it
    # must succeed even though it's not the globally-latest change.
    resp = client.post(f"/api/projects/{project_id}/modifications/{mod1['id']}/revert")
    assert resp.status_code == 200, resp.text
