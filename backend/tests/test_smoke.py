import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Load the FastAPI app with a temporary SQLite database per test."""
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"

    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(backend_dir))
    try:
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        with TestClient(app_module.app) as test_client:
            yield test_client
    finally:
        sys.modules.pop("app", None)
        try:
            sys.path.remove(str(backend_dir))
        except ValueError:
            pass


def test_config_crud_flow(client):
    payload = {
        "name": "ci-smoke",
        "data": {
            "servers": [
                {
                    "ip": "127.0.0.1",
                    "user": "root",
                    "password": "example-password",
                    "port": 22,
                }
            ],
            "commands": ["uname -a"],
        },
    }

    created = client.post("/api/v1/configs", json=payload)
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["success"] is True
    assert created_body["name"] == payload["name"]
    config_id = created_body["id"]

    listed = client.get("/api/v1/configs")
    assert listed.status_code == 200
    assert any(config["id"] == config_id and config["name"] == payload["name"] for config in listed.json())

    fetched = client.get(f"/api/v1/configs/{config_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"] == payload["data"]

    deleted = client.delete(f"/api/v1/configs/{config_id}")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True

    missing = client.get(f"/api/v1/configs/{config_id}")
    assert missing.status_code == 200
    assert missing.json()["success"] is False


def test_execute_endpoint_registers_room_without_opening_ssh(client):
    response = client.post(
        "/api/v1/execute",
        json=[
            {
                "ip": "127.0.0.1",
                "user": "root",
                "password": "example-password",
                "port": 22,
                "commands": ["echo hello"],
                "rowId": "row-1",
            }
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert "room" in body
    assert body["room"]
