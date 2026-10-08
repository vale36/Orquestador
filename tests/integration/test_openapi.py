"""Swagger (/docs) shows the project version: the one in pyproject.toml, which is the
same as the image tag."""

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_openapi_exposes_the_project_version() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]

    response = TestClient(app).get("/openapi.json")

    assert response.json()["info"]["version"] == project["version"]
