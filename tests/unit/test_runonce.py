"""Unit tests for the one-time Data Portal and MQTT command."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from polestar_mqtt import runonce
from polestar_mqtt.config import DEFAULT_POLESTAR_API_BASE_URL
from polestar_mqtt.runonce import main


@pytest.fixture
def run_setup(monkeypatch, requests_mock, tmp_path):
    vin = "LPSVS000000000000"
    for name, value in {
        "POLESTAR_CLIENT_ID": "client-id",
        "POLESTAR_CLIENT_SECRET": "client-secret",
        "POLESTAR_CLIENT_SECRET_EXPIRES_AT": "2099-12-31",
        "POLESTAR_ACCOUNT_ID": "fixture-account",
        "POLESTAR_VIN": vin,
        "MQTT_BASE_TOPIC": "polestar2-test",
        "MQTT_USER": "fixture-user",
        "MQTT_PASSWORD": "fixture-password",
        "MQTT_TOPIC_MAPPING_FILE": str(tmp_path / "mapping.csv"),
        "MQTT_TOPIC_STATE_FILE": str(tmp_path / "state.json"),
    }.items():
        monkeypatch.setenv(name, value)
    requests_mock.post(f"{DEFAULT_POLESTAR_API_BASE_URL}/token", json={
        "accessToken": "access-token-value", "expiresIn": 3600, "tokenType": "Bearer",
    })
    requests_mock.get(f"{DEFAULT_POLESTAR_API_BASE_URL}/v1/vehicles", json={"data": [vin]})
    battery_url = f"{DEFAULT_POLESTAR_API_BASE_URL}/v1/vehicles/{vin}/telemetry/battery"
    requests_mock.get(battery_url, json={
        "data": {"vin": vin, "batteryChargeLevelPercentage": 50},
        "meta": {"vin": vin, "domain": "battery"},
    })
    client = Mock()
    info = Mock(rc=0)
    info.is_published.return_value = True
    client.publish.return_value = info
    client.loop_start.return_value = 0

    def connect(*args):
        client.on_connect(client, None, None, Mock(is_failure=False), None)
        return 0

    client.connect.side_effect = connect
    factory = Mock(return_value=client)
    monkeypatch.setattr(runonce.mqtt, "Client", factory)
    return client, info, factory, battery_url


def test_runonce_confirms_all_topics_and_logs_no_vehicle_data(run_setup, capsys) -> None:
    client, info, _, _ = run_setup
    assert main() == 0
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "data_portal": "successful", "mqtt": "acknowledged", "topics": 4,
    }
    assert info.wait_for_publish.call_count == 4
    assert info.is_published.call_count == 4
    for invocation in client.publish.call_args_list:
        assert invocation.args[0].startswith("polestar2-test/telemetry/battery/")
        assert invocation.kwargs == {"qos": 1, "retain": True}
    client.username_pw_set.assert_called_once_with("fixture-user", "fixture-password")
    client.disconnect.assert_called_once()
    client.loop_stop.assert_called_once()
    for value in ("client-secret", "access-token-value", "LPSVS000000000000", "fixture-account"):
        assert value not in output


def test_runonce_loads_mapping_and_publishes_additional_value(run_setup, tmp_path) -> None:
    client, _, _, _ = run_setup
    (tmp_path / "mapping.csv").write_text(
        "source_path,target_topic\ndata.batteryChargeLevelPercentage,extra/soc\n",
        encoding="utf-8",
    )
    assert main() == 0
    client.publish.assert_any_call("polestar2-test/extra/soc", "50", qos=1, retain=True)
    assert client.publish.call_count == 5


@pytest.mark.parametrize("failure", ["publish", "ack", "connect", "timeout"])
def test_mqtt_failure_returns_error_and_closes_client(run_setup, monkeypatch, failure) -> None:
    client, info, _, _ = run_setup
    if failure == "publish":
        info.rc = 4
    elif failure == "ack":
        info.is_published.return_value = False
    elif failure == "connect":
        client.connect.side_effect = OSError("secret transport detail")
    else:
        client.connect.side_effect = None
        client.connect.return_value = 0
        monkeypatch.setattr(runonce, "MQTT_TIMEOUT_SECONDS", 0)
    assert main() == 1
    client.disconnect.assert_called_once()
    client.loop_stop.assert_called_once()


def test_broker_rejection_does_not_publish(run_setup) -> None:
    client, _, _, _ = run_setup

    def reject(*args):
        client.on_connect(client, None, None, Mock(is_failure=True), None)
        return 0

    client.connect.side_effect = reject
    assert main() == 1
    client.publish.assert_not_called()


def test_invalid_soc_does_not_connect_to_mqtt(run_setup, requests_mock) -> None:
    _, _, factory, url = run_setup
    requests_mock.get(url, json={"data": {}, "meta": {"vin": "LPSVS000000000000"}})
    assert main() == 1
    factory.assert_not_called()


def test_failure_output_does_not_expose_transport_details(run_setup, capsys) -> None:
    client, _, _, _ = run_setup
    client.connect.side_effect = OSError("access-token-value LPSVS000000000000")
    assert main() == 1
    assert capsys.readouterr().out == "Data Portal runonce failed (OSError)\n"


def test_invalid_configuration_does_not_connect(run_setup, monkeypatch) -> None:
    _, _, factory, _ = run_setup
    monkeypatch.setenv("MQTT_PORT", "not-a-number")
    assert main() == 2
    factory.assert_not_called()


def test_inventory_contains_dynamic_and_mapping_topics_only(run_setup, tmp_path) -> None:
    client, _, _, _ = run_setup
    (tmp_path / "mapping.csv").write_text(
        "source_path,target_topic\ndata.batteryChargeLevelPercentage,extra/soc\n",
        encoding="utf-8",
    )
    assert main() == 0
    inventory = json.loads((tmp_path / "state.json").read_text())
    assert inventory == {
        "version": 1,
        "topics": sorted(call.args[0] for call in client.publish.call_args_list),
    }
    assert len(inventory["topics"]) == 5


def test_partial_publication_preserves_previous_inventory(run_setup, tmp_path) -> None:
    _, info, _, _ = run_setup
    state = tmp_path / "state.json"
    previous = '{"version":1,"topics":["old/topic"]}'
    state.write_text(previous)
    info.is_published.side_effect = [True, False]
    assert main() == 1
    assert state.read_text() == previous


def test_inventory_write_failure_fails_run_and_disconnects(run_setup, monkeypatch, tmp_path):
    client, _, _, _ = run_setup
    monkeypatch.setenv("MQTT_TOPIC_STATE_FILE", str(tmp_path / "missing" / "state.json"))
    assert main() == 1
    client.disconnect.assert_called_once()
    client.loop_stop.assert_called_once()
