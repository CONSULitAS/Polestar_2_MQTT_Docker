"""Tests for saving confirmed MQTT topic names without measurement values."""

import json
from pathlib import Path

import pytest

from polestar_mqtt.topic_inventory import TopicInventoryError, save_topic_inventory


def test_saves_unique_sorted_topics_and_replaces_previous_set(tmp_path):
    path = tmp_path / "state.json"
    save_topic_inventory(path, ["z/soc", "a/charging", "z/soc"])
    assert json.loads(path.read_text()) == {
        "version": 1, "topics": ["a/charging", "z/soc"],
    }
    save_topic_inventory(path, ["new/topic"])
    assert json.loads(path.read_text())["topics"] == ["new/topic"]
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replace_preserves_previous_file_and_redacts_error(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("previous")

    def deny_replace(*args):
        raise PermissionError("private-path")

    monkeypatch.setattr(Path, "replace", deny_replace)
    with pytest.raises(TopicInventoryError) as caught:
        save_topic_inventory(path, ["new/topic"])
    assert "private-path" not in str(caught.value)
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]
