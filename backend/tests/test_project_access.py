"""Reviewers see only their own projects; admins/owners see all.

Run with:
    cd backend && python -m pytest tests/test_project_access.py -v
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.api.polygons import router as polygons_router
from app.api.projects import router as projects_router
from app.database import get_db
from app.models.polygon import Polygon
from app.models.project import Project


@pytest.fixture
def project_client(db_session):
    app = FastAPI()
    app.include_router(projects_router, prefix="/projects")
    app.include_router(polygons_router, prefix="/polygons")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


def _make_project(db_session, creator_id, name="proj") -> Project:
    p = Project(
        name=name,
        bounds=f"SRID=4326;{box(-1, -1, 1, 1).wkt}",
        created_by=creator_id,
        status="pending",
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_polygon(db_session, project_id) -> Polygon:
    poly = Polygon(
        project_id=project_id,
        geometry=f"SRID=4326;{box(0, 0, 0.5, 0.5).wkt}",
        status="detected",
    )
    db_session.add(poly)
    db_session.commit()
    db_session.refresh(poly)
    return poly


def test_list_projects_reviewer_sees_only_own(
    project_client, db_session, make_user, auth_headers
):
    reviewer_a = make_user(role="reviewer")
    reviewer_b = make_user(role="reviewer")
    _make_project(db_session, reviewer_a.id, "a-1")
    _make_project(db_session, reviewer_a.id, "a-2")
    _make_project(db_session, reviewer_b.id, "b-1")

    resp = project_client.get("/projects", headers=auth_headers(reviewer_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    names = {p["name"] for p in body["projects"]}
    assert names == {"a-1", "a-2"}


def test_list_projects_admin_sees_all(
    project_client, db_session, make_user, auth_headers
):
    admin = make_user(role="admin")
    reviewer = make_user(role="reviewer")
    r_proj = _make_project(db_session, reviewer.id, "r-1")
    a_proj = _make_project(db_session, admin.id, "a-1")

    resp = project_client.get("/projects?limit=100", headers=auth_headers(admin))
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()["projects"]}
    assert str(r_proj.id) in ids
    assert str(a_proj.id) in ids


def test_list_projects_owner_sees_all(
    project_client, db_session, make_user, auth_headers
):
    owner = make_user(role="owner")
    reviewer = make_user(role="reviewer")
    r_proj = _make_project(db_session, reviewer.id, "r-1")

    resp = project_client.get("/projects?limit=100", headers=auth_headers(owner))
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()["projects"]}
    assert str(r_proj.id) in ids


def test_get_project_other_reviewers_returns_404(
    project_client, db_session, make_user, auth_headers
):
    reviewer_a = make_user(role="reviewer")
    reviewer_b = make_user(role="reviewer")
    b_proj = _make_project(db_session, reviewer_b.id)

    resp = project_client.get(
        f"/projects/{b_proj.id}", headers=auth_headers(reviewer_a)
    )
    assert resp.status_code == 404


def test_get_project_admin_can_read_any(
    project_client, db_session, make_user, auth_headers
):
    admin = make_user(role="admin")
    reviewer = make_user(role="reviewer")
    proj = _make_project(db_session, reviewer.id)

    resp = project_client.get(f"/projects/{proj.id}", headers=auth_headers(admin))
    assert resp.status_code == 200


def test_patch_project_other_reviewers_returns_404(
    project_client, db_session, make_user, auth_headers
):
    reviewer_a = make_user(role="reviewer")
    reviewer_b = make_user(role="reviewer")
    b_proj = _make_project(db_session, reviewer_b.id)

    resp = project_client.patch(
        f"/projects/{b_proj.id}",
        headers=auth_headers(reviewer_a),
        json={"name": "hacked"},
    )
    assert resp.status_code == 404


def test_polygons_for_project_other_reviewers_returns_404(
    project_client, db_session, make_user, auth_headers
):
    reviewer_a = make_user(role="reviewer")
    reviewer_b = make_user(role="reviewer")
    b_proj = _make_project(db_session, reviewer_b.id)

    resp = project_client.get(
        f"/polygons/project/{b_proj.id}", headers=auth_headers(reviewer_a)
    )
    assert resp.status_code == 404


def test_get_polygon_by_id_other_reviewers_returns_404(
    project_client, db_session, make_user, auth_headers
):
    reviewer_a = make_user(role="reviewer")
    reviewer_b = make_user(role="reviewer")
    b_proj = _make_project(db_session, reviewer_b.id)
    b_poly = _make_polygon(db_session, b_proj.id)

    resp = project_client.get(
        f"/polygons/{b_poly.id}", headers=auth_headers(reviewer_a)
    )
    assert resp.status_code == 404


def test_get_polygon_by_id_owner_works(
    project_client, db_session, make_user, auth_headers
):
    reviewer = make_user(role="reviewer")
    proj = _make_project(db_session, reviewer.id)
    poly = _make_polygon(db_session, proj.id)

    resp = project_client.get(
        f"/polygons/{poly.id}", headers=auth_headers(reviewer)
    )
    assert resp.status_code == 200
