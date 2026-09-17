"""Unit tests for the authentication-only command."""

from __future__ import annotations

import json

import requests_mock as requests_mock_module

from polestar_mqtt.auth_check import main
from polestar_mqtt.config import DEFAULT_POLESTAR_API_BASE_URL


def set_valid_environment(monkeypatch) -> None:
    values = {
        "POLESTAR_CLIENT_ID": "client-id",
        "POLESTAR_CLIENT_SECRET": "client-secret",
        "POLESTAR_CLIENT_SECRET_EXPIRES_AT": "2099-12-31",
        "POLESTAR_ACCOUNT_ID": "12345678-1234-1234-1234-123456789abc",
        "POLESTAR_VIN": "LPSVS000000000000",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_auth_check_prints_only_safe_metadata(
    monkeypatch,
    capsys,
    requests_mock: requests_mock_module.Mocker,
) -> None:
    set_valid_environment(monkeypatch)
    requests_mock.post(f"{DEFAULT_POLESTAR_API_BASE_URL}/token", json={
        "accessToken": "access-token-value",
        "expiresIn": 3600,
        "tokenType": "Bearer",
    })

    assert main() == 0
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "authentication": "successful",
        "expires_in": 3600.0,
        "token_type": "Bearer",
    }
    assert "access-token-value" not in output
    assert "client-secret" not in output


def test_auth_check_returns_nonzero_for_missing_configuration(
    monkeypatch,
    capsys,
) -> None:
    for name in (
        "POLESTAR_CLIENT_ID",
        "POLESTAR_CLIENT_SECRET",
        "POLESTAR_CLIENT_SECRET_EXPIRES_AT",
        "POLESTAR_ACCOUNT_ID",
        "POLESTAR_VIN",
    ):
        monkeypatch.delenv(name, raising=False)

    assert main() == 2
    assert "configuration error" in capsys.readouterr().out


def test_auth_check_returns_nonzero_without_leaking_secret(
    monkeypatch,
    capsys,
    requests_mock: requests_mock_module.Mocker,
) -> None:
    set_valid_environment(monkeypatch)
    requests_mock.post(
        f"{DEFAULT_POLESTAR_API_BASE_URL}/token",
        status_code=401,
        json={
            "error": "invalid_client",
            "error_description": "rejected client-secret",
            "timestamp": "2026-01-01T00:00:00Z",
        },
    )

    assert main() == 1
    output = capsys.readouterr().out
    assert "HTTP 401" in output
    assert "client-secret" not in output
    assert "[REDACTED]" in output

