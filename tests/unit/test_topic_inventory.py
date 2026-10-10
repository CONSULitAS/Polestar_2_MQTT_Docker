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
