"""Tests for saving confirmed MQTT topic names without measurement values."""

import json
from pathlib import Path

import pytest

from polestar_mqtt.topic_inventory import (
    TopicInventoryError, load_topic_inventory, save_topic_inventory,
)


BATTERY = "/v1/vehicles/{vin}/telemetry/battery"


# Das Inventar speichert eindeutige, sortierte Topics und ersetzt den bisherigen Stand.
def test_saves_unique_sorted_topics_and_replaces_previous_set(tmp_path):
    path = tmp_path / "state.json"
    save_topic_inventory(path, {BATTERY: ["z/soc", "a/charging", "z/soc"]})
    assert json.loads(path.read_text()) == {
        "version": 2, "endpoints": {BATTERY: ["a/charging", "z/soc"]}, "unassigned_topics": [],
    }
    save_topic_inventory(path, {BATTERY: ["new/topic"]})
    assert load_topic_inventory(path) == ({BATTERY: ["new/topic"]}, [])
    assert list(tmp_path.iterdir()) == [path]


# Ein fehlgeschlagener Dateiaustausch erhält das alte Inventar und maskiert Fehlerdetails.
def test_failed_replace_preserves_previous_file_and_redacts_error(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("previous")

    def deny_replace(*args):
        raise PermissionError("private-path")

    monkeypatch.setattr(Path, "replace", deny_replace)
    with pytest.raises(TopicInventoryError) as caught:
        save_topic_inventory(path, {BATTERY: ["new/topic"]})
    assert "private-path" not in str(caught.value)
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]


# Ein fehlendes Inventar startet ohne frühere Zuordnungen.
def test_missing_inventory_starts_empty(tmp_path):
    assert load_topic_inventory(tmp_path / "missing.json") == ({}, [])


# Die alte flache Topic-Liste bleibt ohne geratene Endpunktzuordnung erhalten.
def test_version_one_topics_survive_migration(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1, "topics": ["old/absolute", "old/dynamic"]}))
    endpoints, unassigned = load_topic_inventory(path)
    endpoints[BATTERY] = ["new/battery"]
    save_topic_inventory(path, endpoints, unassigned_topics=unassigned)
    assert load_topic_inventory(path) == (
        {BATTERY: ["new/battery"]}, ["old/absolute", "old/dynamic"],
    )


@pytest.mark.parametrize("payload", [
    [], {}, {"version": True, "topics": []}, {"version": 3, "topics": []},
    {"version": 1, "topics": "not-a-list"}, {"version": 1, "topics": ["bad/#"]},
    {"version": 2, "endpoints": {"invalid": []}, "unassigned_topics": []},
    {"version": 2, "endpoints": {BATTERY: [False]}, "unassigned_topics": []},
])
# Ungültige Inventare werden abgelehnt und nicht durch einen leeren Stand ersetzt.
def test_invalid_inventory_is_preserved(tmp_path, payload):
    path = tmp_path / "state.json"
    original = json.dumps(payload)
    path.write_text(original)
    with pytest.raises(TopicInventoryError):
        load_topic_inventory(path)
    assert path.read_text() == original


# Leseprobleme werden ohne Offenlegung des Dateipfads gemeldet.
def test_inventory_read_error_is_redacted(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("private-path")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(TopicInventoryError) as error:
        load_topic_inventory(tmp_path / "state.json")
    assert "private-path" not in str(error.value)


@pytest.fixture
def managed_config(tmp_path):
    from types import SimpleNamespace

    return SimpleNamespace(
        mqtt_topic_state_file=tmp_path / "managed.json", mqtt_broker="broker.test",
        mqtt_port=1883, mqtt_base_topic="test", vin="LPSVS000000000000", account_id="account",
    )


# Alte Inventare erhalten keinen Löschanspruch ohne Broker- und Instanzzuordnung.
def test_unbound_inventory_is_migrated_without_deletion_rights(managed_config):
    from polestar_mqtt.topic_inventory import ManagedTopicInventory

    path = managed_config.mqtt_topic_state_file
    save_topic_inventory(path, {BATTERY: ["old/topic"]})
    with ManagedTopicInventory(managed_config) as inventory:
        assert inventory.endpoints == {}
        assert inventory.unassigned == ["old/topic"]
        assert inventory.begin(BATTERY, ["test/new"]) == []
        inventory.finish(BATTERY, ["test/new"])
    assert json.loads(path.read_text())["unassigned_topics"] == ["old/topic"]


@pytest.mark.parametrize("attribute,value", [
    ("mqtt_broker", "another.test"), ("mqtt_port", 8883), ("mqtt_base_topic", "other"),
    ("vin", "LPSVS000000000001"), ("account_id", "other"),
])
# Ein Wechsel des Brokers oder Publishers überschreibt kein vorhandenes Inventar.
def test_identity_change_preserves_inventory(managed_config, attribute, value):
    from polestar_mqtt.topic_inventory import ManagedTopicInventory

    with ManagedTopicInventory(managed_config) as inventory:
        inventory.save()
    before = managed_config.mqtt_topic_state_file.read_text()
    setattr(managed_config, attribute, value)
    with pytest.raises(TopicInventoryError):
        with ManagedTopicInventory(managed_config):
            pytest.fail("Foreign inventory accepted")
    assert managed_config.mqtt_topic_state_file.read_text() == before


# Eine zweite Instanz scheitert an derselben Sperre; nach Freigabe ist ein Neustart möglich.
def test_inventory_lock_excludes_parallel_writer(managed_config):
    from polestar_mqtt.topic_inventory import ManagedTopicInventory

    with ManagedTopicInventory(managed_config):
        with pytest.raises(TopicInventoryError):
            with ManagedTopicInventory(managed_config):
                pytest.fail("Concurrent inventory access accepted")
    with ManagedTopicInventory(managed_config) as inventory:
        inventory.save()


@pytest.mark.parametrize("topic", [
    "test/container", "test/container/connected", "test/container/credentials/status",
    "test/charging/removed/log", "test/telemetry/removed/log/timestamp",
])
# Auch manipulierte Inventare dürfen geschützte Status- und Diagnose-Topics nicht löschen.
def test_protected_inventory_topics_stop_loading(managed_config, topic):
    from polestar_mqtt.topic_inventory import ManagedTopicInventory

    with ManagedTopicInventory(managed_config) as inventory:
        inventory.endpoints[BATTERY] = [topic]
        inventory.save()
    before = managed_config.mqtt_topic_state_file.read_text()
    with pytest.raises(TopicInventoryError):
        with ManagedTopicInventory(managed_config):
            pytest.fail("Protected inventory accepted")
    assert managed_config.mqtt_topic_state_file.read_text() == before


# Ein Endpunkt darf keine Topics eines fehlgeschlagenen oder entfernten Endpunkts übernehmen.
def test_plan_cannot_take_another_endpoints_history(managed_config):
    from polestar_mqtt.topic_inventory import ManagedTopicInventory

    with ManagedTopicInventory(managed_config) as inventory:
        inventory.endpoints[BATTERY] = ["test/shared"]
        with pytest.raises(TopicInventoryError):
            inventory.validate_plan({"/v1/vehicles/{vin}/telemetry/exterior": ["test/shared"]})
