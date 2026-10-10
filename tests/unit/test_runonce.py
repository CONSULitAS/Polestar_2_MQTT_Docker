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
    for endpoint in runonce.build_endpoint_catalog(
        runonce.load_openapi_document(tmp_path / "missing")
    ):
        requests_mock.get(
            DEFAULT_POLESTAR_API_BASE_URL + endpoint.request_path(vin),
            json={"data": {}},
        )
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


# Der Einmallauf bestätigt alle MQTT-Ausgaben, ohne Fahrzeugdaten zu protokollieren.
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


# Ein lokales CSV-Mapping ergänzt die dynamische Battery-Ausgabe um zusätzliche Ziele.
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
# MQTT-Fehler führen zum Fehlerstatus und zum Schließen der Verbindung.
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


# Lehnt der Broker die Verbindung ab, werden keine Nutzwerte veröffentlicht.
def test_broker_rejection_does_not_publish(run_setup) -> None:
    client, _, _, _ = run_setup

    def reject(*args):
        client.on_connect(client, None, None, Mock(is_failure=True), None)
        return 0

    client.connect.side_effect = reject
    assert main() == 1
    client.publish.assert_not_called()


# Ohne gültigen SoC oder andere Nutzdaten wird keine MQTT-Verbindung geöffnet.
def test_invalid_soc_does_not_connect_to_mqtt(run_setup, requests_mock) -> None:
    _, _, factory, url = run_setup
    requests_mock.get(url, json={"data": {}, "meta": {"vin": "LPSVS000000000000"}})
    assert main() == 1
    factory.assert_not_called()


# Transportfehler werden ohne möglicherweise vertrauliche Exception-Inhalte ausgegeben.
def test_failure_output_does_not_expose_transport_details(run_setup, capsys) -> None:
    client, _, _, _ = run_setup
    client.connect.side_effect = OSError("access-token-value LPSVS000000000000")
    assert main() == 1
    assert capsys.readouterr().out == "Data Portal runonce failed (OSError)\n"


# Eine ungültige Konfiguration verhindert den Verbindungsaufbau.
def test_invalid_configuration_does_not_connect(run_setup, monkeypatch) -> None:
    _, _, factory, _ = run_setup
    monkeypatch.setenv("MQTT_PORT", "not-a-number")
    assert main() == 2
    factory.assert_not_called()


# Das Inventar enthält genau die erfolgreich publizierten dynamischen und Mapping-Topics.
def test_inventory_contains_dynamic_and_mapping_topics_only(run_setup, tmp_path) -> None:
    client, _, _, _ = run_setup
    (tmp_path / "mapping.csv").write_text(
        "source_path,target_topic\ndata.batteryChargeLevelPercentage,extra/soc\n",
        encoding="utf-8",
    )
    assert main() == 0
    inventory = json.loads((tmp_path / "state.json").read_text())
    assert inventory["version"] == 2
    assert inventory["unassigned_topics"] == []
    assert inventory["endpoints"]["/v1/vehicles/{vin}/telemetry/battery"] == sorted(
        call.args[0] for call in client.publish.call_args_list
    )
    assert sum(len(topics) for topics in inventory["endpoints"].values()) == 5


# Fehlende MQTT-Bestätigungen lassen das bisherige Topic-Inventar unverändert.
def test_partial_publication_preserves_previous_inventory(run_setup, tmp_path) -> None:
    _, info, _, _ = run_setup
    state = tmp_path / "state.json"
    previous = '{"version":1,"topics":["old/topic"]}'
    state.write_text(previous)
    info.is_published.side_effect = [True, False]
    assert main() == 1
    assert state.read_text() == previous


# Ein Schreibfehler am Inventar beendet den Lauf mit Fehler und schließt MQTT.
def test_inventory_write_failure_fails_run_and_disconnects(run_setup, monkeypatch, tmp_path):
    client, _, _, _ = run_setup
    monkeypatch.setenv("MQTT_TOPIC_STATE_FILE", str(tmp_path / "missing" / "state.json"))
    assert main() == 1
    client.disconnect.assert_called_once()
    client.loop_stop.assert_called_once()


# Ungültiges OpenAPI-JSON verhindert sämtliche API- und MQTT-Verbindungen.
def test_invalid_openapi_stops_before_network(run_setup, tmp_path, monkeypatch, requests_mock):
    _, _, factory, _ = run_setup
    local = tmp_path / "invalid.json"
    local.write_text("invalid", encoding="utf-8")
    monkeypatch.setenv("POLESTAR_OPENAPI_FILE", str(local))
    assert main() == 2
    assert requests_mock.call_count == 0
    factory.assert_not_called()


# Die OpenAPI-Datei wird pro Einmallauf genau einmal geladen.
def test_openapi_loaded_once_per_start(run_setup, monkeypatch):
    loader = Mock(wraps=runonce.load_openapi_document)
    monkeypatch.setattr(runonce, "load_openapi_document", loader)
    assert main() == 0
    loader.assert_called_once()


# Ein unbekannter Katalogpfad wird vor dem ersten Netzwerkzugriff abgelehnt.
def test_unsafe_catalog_stops_before_network(run_setup, tmp_path, monkeypatch, requests_mock):
    _, _, factory, _ = run_setup
    document = runonce.load_openapi_document(tmp_path / "missing")
    document["paths"]["/unexpected"] = {"get": {"responses": {"200": {}}}}
    local = tmp_path / "unsafe.json"
    local.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setenv("POLESTAR_OPENAPI_FILE", str(local))
    assert main() == 2
    assert requests_mock.call_count == 0
    factory.assert_not_called()


# Serverangaben aus OpenAPI dürfen die konfigurierte API-Basis niemals ersetzen.
def test_openapi_servers_never_replace_configured_api_base(
    run_setup, tmp_path, monkeypatch, requests_mock,
):
    document = runonce.load_openapi_document(tmp_path / "missing")
    injected = [{"url": "https://untrusted.invalid/collect"}]
    document["servers"] = injected
    for item in document["paths"].values():
        item["servers"] = injected
        for method in ("get", "post"):
            if method in item:
                item[method]["servers"] = injected
    local = tmp_path / "servers.json"
    local.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setenv("POLESTAR_OPENAPI_FILE", str(local))
    assert main() == 0
    assert len(requests_mock.request_history) == 17
    assert all(
        request.url.startswith(DEFAULT_POLESTAR_API_BASE_URL + "/")
        for request in requests_mock.request_history
    )


# Alle Katalog-Scopes gelten auch für einen neuen Endpunkt und die Erneuerung nach 401.
def test_runonce_requests_catalog_scopes_on_initial_token_and_401_retry(
    run_setup, tmp_path, monkeypatch, requests_mock,
):
    _, _, _, battery_url = run_setup
    document = runonce.load_openapi_document(tmp_path / "missing")
    document["paths"]["/v1/vehicles/{vin}/telemetry/new-field"] = {
        "get": {"responses": {"200": {}}, "x-required-scopes": [
            "test/new", "pdp-telemetry/battery", "test/new",
        ]},
    }
    local = tmp_path / "scopes.json"
    local.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setenv("POLESTAR_OPENAPI_FILE", str(local))
    # Synthetic VIN: requests-mock answers locally; no live vehicle is queried.
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL + "/v1/vehicles/LPSVS000000000000/telemetry/new-field",
        json={"data": {}},
    )
    requests_mock.get(battery_url, [
        {"status_code": 401, "json": {}},
        {"json": {"data": {
            "vin": "LPSVS000000000000", "batteryChargeLevelPercentage": 50,
        }, "meta": {"vin": "LPSVS000000000000"}}},
    ])
    assert main() == 0
    expected = " ".join(sorted({
        scope for item in document["paths"].values()
        for scope in item.get("get", {}).get("x-required-scopes", [])
    }))
    token_requests = [r for r in requests_mock.request_history if r.method == "POST"]
    assert len(token_requests) == 2
    assert all(r.json()["scope"] == expected for r in token_requests)
    assert any(r.url.endswith("/telemetry/new-field") for r in requests_mock.request_history)


@pytest.mark.parametrize("response", [
    {"status_code": 404, "json": {}},
    {"status_code": 403, "json": {}},
    {"text": "invalid JSON"},
])
# Fehler anderer Endpunkte erlauben die Battery-Ausgabe und werden als Teilbetrieb gemeldet.
def test_other_endpoint_failure_still_publishes_valid_battery(
    run_setup, requests_mock, response, capsys, tmp_path,
):
    client, _, _, _ = run_setup
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL
        + "/v1/vehicles/LPSVS000000000000/charging/is-at-charge-location",
        **response,
    )
    assert main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary == {
        "data_portal": "partial", "mqtt": "acknowledged", "topics": 4,
        "failed_endpoints": 1,
    }
    assert client.publish.call_count == 4
    assert (tmp_path / "state.json").is_file()
    assert requests_mock.call_count == 17


# Ein Battery-Ausfall ohne andere Nutzdaten lässt MQTT und Inventar unverändert.
def test_failed_battery_preserves_inventory_and_does_not_publish(
    run_setup, requests_mock, tmp_path,
):
    _, _, factory, battery_url = run_setup
    state = tmp_path / "state.json"
    previous = '{"version":1,"topics":["previous/topic"]}'
    state.write_text(previous)
    requests_mock.get(battery_url, status_code=404, json={})
    assert main() == 1
    factory.assert_not_called()
    assert state.read_text() == previous
    assert requests_mock.call_count == 17


# Neue Felder, Metadaten und Arraywerte erscheinen unter der jeweiligen Endpunktwurzel.
def test_generic_endpoint_keeps_data_meta_and_arrays(run_setup, requests_mock, tmp_path):
    client, _, _, _ = run_setup
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL + "/v1/vehicles/LPSVS000000000000/telemetry/exterior",
        json={"data": {"newField": [True, 7]}, "meta": {"domain": "exterior"}},
    )
    assert main() == 0
    root = "polestar2-test/telemetry/exterior"
    client.publish.assert_any_call(root + "/data/newField/0", "true", qos=1, retain=True)
    client.publish.assert_any_call(root + "/data/newField/1", "7", qos=1, retain=True)
    client.publish.assert_any_call(root + "/meta/domain", "exterior", qos=1, retain=True)
    inventory = json.loads((tmp_path / "state.json").read_text())
    assert sum(len(topics) for topics in inventory["endpoints"].values()) == 7


# Ein Battery-Ausfall blockiert die Veröffentlichung anderer erfolgreicher Antworten nicht.
def test_battery_failure_does_not_block_other_publications(run_setup, requests_mock, capsys):
    client, _, _, battery_url = run_setup
    requests_mock.get(battery_url, status_code=404, json={})
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL + "/v1/vehicles/LPSVS000000000000/telemetry/exterior",
        json={"data": {"newField": 7}},
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["data_portal"] == "partial"
    client.publish.assert_called_once_with(
        "polestar2-test/telemetry/exterior/data/newField", "7", qos=1, retain=True,
    )


# Ein Mapping darf kein dynamisches Topic eines anderen Endpunkts überschreiben.
def test_mapping_collision_with_other_endpoint_stops_before_publish(
    run_setup, requests_mock, tmp_path,
):
    _, _, factory, _ = run_setup
    (tmp_path / "mapping.csv").write_text(
        "source_path,target_topic\ndata.batteryChargeLevelPercentage,telemetry/exterior/data/value\n",
        encoding="utf-8",
    )
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL + "/v1/vehicles/LPSVS000000000000/telemetry/exterior",
        json={"data": {"value": 7}},
    )
    assert main() == 1
    factory.assert_not_called()


# Ein temporärer Endpunktfehler erhält seine früheren Topics trotz erfolgreicher Battery-Ausgabe.
def test_endpoint_failure_preserves_history_during_partial_success(
    run_setup, requests_mock, tmp_path,
):
    from polestar_mqtt.topic_inventory import load_topic_inventory, save_topic_inventory

    endpoint = "/v1/vehicles/{vin}/telemetry/exterior"
    state = tmp_path / "state.json"
    previous = ["polestar2-test/telemetry/exterior/data/old"]
    save_topic_inventory(state, {endpoint: previous})
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL + endpoint.replace("{vin}", "LPSVS000000000000"),
        status_code=404, json={"error": {"code": "TEMPORARY", "message": "Try later"}},
    )
    assert main() == 0
    endpoints, _ = load_topic_inventory(state)
    assert endpoints[endpoint] == previous
    assert "/v1/vehicles/{vin}/telemetry/battery" in endpoints


# Bereits bestätigte Endpunkte bleiben gespeichert, wenn ein späterer Publish scheitert.
def test_later_publish_failure_preserves_confirmed_endpoint_update(
    run_setup, requests_mock, tmp_path,
):
    from polestar_mqtt.topic_inventory import load_topic_inventory, save_topic_inventory

    _, info, _, _ = run_setup
    early = "/v1/vehicles/{vin}/charging/amp-limit"
    battery = "/v1/vehicles/{vin}/telemetry/battery"
    state = tmp_path / "state.json"
    save_topic_inventory(state, {battery: ["old/battery"], early: ["old/charging"]})
    requests_mock.get(
        DEFAULT_POLESTAR_API_BASE_URL + early.replace("{vin}", "LPSVS000000000000"),
        json={"data": {"value": 16}},
    )
    info.is_published.side_effect = [True, False]
    assert main() == 1
    endpoints, _ = load_topic_inventory(state)
    assert endpoints[battery] == ["old/battery"]
    assert endpoints[early] == ["polestar2-test/charging/amp-limit/data/value"]


# Ein beschädigtes Inventar wird vor Netzwerkzugriffen erkannt und nicht überschrieben.
def test_corrupt_inventory_stops_before_network(run_setup, tmp_path, requests_mock):
    _, _, factory, _ = run_setup
    state = tmp_path / "state.json"
    state.write_text("broken")
    assert main() == 1
    assert requests_mock.call_count == 0
    factory.assert_not_called()
    assert state.read_text() == "broken"
