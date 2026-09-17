"""Unit tests for the one-time live SoC check command."""

from __future__ import annotations

import json

import requests_mock as requests_mock_module

from polestar_mqtt.config import DEFAULT_POLESTAR_API_BASE_URL
from polestar_mqtt.soc_check import main


def test_soc_check_prints_only_validated_soc(
    monkeypatch,
    capsys,
    requests_mock: requests_mock_module.Mocker,
) -> None:
    vin = "LPSVS000000000000"
    values = {
        "POLESTAR_CLIENT_ID": "client-id",
        "POLESTAR_CLIENT_SECRET": "client-secret",
        "POLESTAR_CLIENT_SECRET_EXPIRES_AT": "2099-12-31",
        "POLESTAR_ACCOUNT_ID": "12345678-1234-1234-1234-123456789abc",
        "POLESTAR_VIN": vin,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    requests_mock.post(f"{DEFAULT_POLESTAR_API_BASE_URL}/token", json={
        "accessToken": "access-token-value",
        "expiresIn": 3600,
        "tokenType": "Bearer",
    })
    requests_mock.get(
        f"{DEFAULT_POLESTAR_API_BASE_URL}/v1/vehicles",
        json={"data": [vin], "meta": {"count": 1}},
    )
    requests_mock.get(
        f"{DEFAULT_POLESTAR_API_BASE_URL}/v1/vehicles/{vin}/telemetry/battery",
        json={
            "data": {"vin": vin, "batteryChargeLevelPercentage": 50},
            "meta": {"vin": vin, "domain": "battery"},
        },
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert json.loads(output) == {"live_data": "successful", "soc_percent": 50.0}
    for sensitive_value in (
        "client-secret",
        "access-token-value",
        vin,
        values["POLESTAR_ACCOUNT_ID"],
    ):
        assert sensitive_value not in output

