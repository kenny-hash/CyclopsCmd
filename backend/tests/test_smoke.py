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


def test_execute_rejects_invalid_ip_port_and_empty_command(client):
    response = client.post(
        "/api/v1/execute",
        json=[
            {
                "ip": "not-an-ip",
                "user": "root",
                "password": "example-password",
                "port": 70000,
                "commands": [""],
                "rowId": "row-1",
            }
        ],
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"]
    detail_locations = [tuple(detail["loc"]) for detail in body["error"]["details"]]
    assert ("body", 0, "ip") in detail_locations
    assert ("body", 0, "port") in detail_locations
    assert ("body", 0, "commands", 0) in detail_locations


def test_execute_rejects_enabled_jump_server_without_required_fields(client):
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
                "jumpServer": {"enabled": True, "port": 22},
            }
        ],
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any("Jump server IP, username and password" in detail["msg"] for detail in body["error"]["details"])


def test_execute_accepts_enabled_jump_server_with_password(client):
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
                "jumpServer": {
                    "enabled": True,
                    "ip": "127.0.0.1",
                    "user": "jump-user",
                    "password": "jump-password",
                    "port": 22,
                },
            }
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert "room" in body
    assert body["room"]


def test_jump_connection_key_includes_password_fingerprint(client):
    import app as app_module

    first = app_module.build_jump_connection_key("192.0.2.10", "jump-user", "first-password", 22)
    second = app_module.build_jump_connection_key("192.0.2.10", "jump-user", "second-password", 22)

    assert first != second
    assert "first-password" not in first
    assert "second-password" not in second


def test_via_jump_connection_key_isolated_by_jump_and_target_password(client):
    import app as app_module

    jump_a = app_module.build_jump_connection_key("192.0.2.10", "jump-user", "jump-a", 22)
    jump_b = app_module.build_jump_connection_key("192.0.2.11", "jump-user", "jump-b", 22)

    via_a = app_module.build_via_jump_connection_key("10.0.0.5", "root", "target-a", 22, jump_a)
    via_b = app_module.build_via_jump_connection_key("10.0.0.5", "root", "target-a", 22, jump_b)
    via_c = app_module.build_via_jump_connection_key("10.0.0.5", "root", "target-b", 22, jump_a)

    assert via_a != via_b
    assert via_a != via_c
    assert "target-a" not in via_a
    assert "jump-a" not in via_a


def test_sanitize_connection_key_redacts_fingerprints(client):
    import app as app_module

    jump = app_module.build_jump_connection_key("192.0.2.10", "jump-user", "jump-secret", 22)
    via = app_module.build_via_jump_connection_key("10.0.0.5", "root", "target-secret", 22, jump)
    sanitized = app_module.sanitize_connection_key(via)

    assert "jump-secret" not in sanitized
    assert "target-secret" not in sanitized
    assert app_module.credential_fingerprint("jump-secret") not in sanitized
    assert app_module.credential_fingerprint("target-secret") not in sanitized
    assert "<redacted>" in sanitized


def test_describe_ssh_exception_includes_safe_channel_details(client):
    import asyncssh
    import app as app_module

    exc = asyncssh.misc.ChannelOpenError(1, "administratively prohibited")
    diagnostics = app_module.describe_ssh_exception(exc)

    assert diagnostics["exception_type"] == "ChannelOpenError"
    assert diagnostics["code"] == 1
    assert diagnostics["reason"] == "administratively prohibited"
