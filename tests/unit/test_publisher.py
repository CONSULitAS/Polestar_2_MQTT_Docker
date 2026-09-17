"""Unit tests for the migrated MQTT publishing boundary."""

from __future__ import annotations

from unittest.mock import Mock, call
from pathlib import Path
import traceback

import pytest

from polestar_mqtt.publisher import (
    TopicMappingError,
    flatten_json_topics,
    load_topic_mapping,
    parse_source_path,
    normalize_topic_segment,
    parse_topic_mapping_csv,
    publish_json_topics,
    resolve_topic_mapping,
    validate_publish_topic,
)


def test_flattens_nested_objects_and_arrays_in_json_order() -> None:
    payload = {
        "data": {
            "batteryChargeLevelPercentage": 77,
            "timestamp": {"seconds": "1788362002", "nanos": 200_583_773},
            "warnings": ["first", None, False],
        },
        "meta": {"domain": "battery"},
    }

    assert flatten_json_topics("polestar2/telemetry/battery", payload) == [
        (
            "polestar2/telemetry/battery/data/batteryChargeLevelPercentage",
            77,
        ),
        ("polestar2/telemetry/battery/data/timestamp/seconds", "1788362002"),
        ("polestar2/telemetry/battery/data/timestamp/nanos", 200_583_773),
        ("polestar2/telemetry/battery/data/warnings/0", "first"),
        ("polestar2/telemetry/battery/data/warnings/1", None),
        ("polestar2/telemetry/battery/data/warnings/2", False),
        ("polestar2/telemetry/battery/meta/domain", "battery"),
    ]


def test_empty_containers_create_no_scalar_topics() -> None:
    assert flatten_json_topics("polestar2/telemetry/battery", {"empty": []}) == []


def test_new_json_fields_automatically_create_topics() -> None:
    payload = {
        "data": {
            "futureTelemetry": {
                "newScalar": 12.5,
                "newState": "available",
            }
        }
    }

    assert flatten_json_topics("polestar2/telemetry/battery", payload) == [
        ("polestar2/telemetry/battery/data/futureTelemetry/newScalar", 12.5),
        (
            "polestar2/telemetry/battery/data/futureTelemetry/newState",
            "available",
        ),
    ]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("batteryChargeLevelPercentage", "batteryChargeLevelPercentage"),
        ("charge/status", "charge%2Fstatus"),
        ("wild+card#", "wild%2Bcard%23"),
        ("space key", "space%20key"),
        ("größer", "gr%C3%B6%C3%9Fer"),
        ("%EMPTY", "%25EMPTY"),
        ("", "%EMPTY"),
    ],
)
def test_normalizes_json_keys_as_single_mqtt_topic_segments(
    key: str,
    expected: str,
) -> None:
    assert normalize_topic_segment(key) == expected
    assert flatten_json_topics("polestar2/root", {key: 1}) == [
        (f"polestar2/root/{expected}", 1)
    ]


def test_rejects_non_json_values() -> None:
    with pytest.raises(TypeError, match="Unsupported JSON value type"):
        flatten_json_topics("polestar2/telemetry/battery", object())


def test_publishes_scalar_leaves_retained_with_qos_one() -> None:
    client = Mock()
    payload = {
        "text": "available",
        "emptyText": "",
        "count": 2,
        "ratio": 12.5,
        "enabled": True,
        "missing": None,
        "array": [1, "second"],
    }

    published_topics = publish_json_topics(client, "polestar2/root", payload)

    assert published_topics == [
        "polestar2/root/text",
        "polestar2/root/emptyText",
        "polestar2/root/count",
        "polestar2/root/ratio",
        "polestar2/root/enabled",
        "polestar2/root/missing",
        "polestar2/root/array/0",
        "polestar2/root/array/1",
    ]
    assert client.publish.call_args_list == [
        call("polestar2/root/text", "available", qos=1, retain=True),
        call("polestar2/root/emptyText", '""', qos=1, retain=True),
        call("polestar2/root/count", "2", qos=1, retain=True),
        call("polestar2/root/ratio", "12.5", qos=1, retain=True),
        call("polestar2/root/enabled", "true", qos=1, retain=True),
        call("polestar2/root/missing", "null", qos=1, retain=True),
        call("polestar2/root/array/0", "1", qos=1, retain=True),
        call("polestar2/root/array/1", "second", qos=1, retain=True),
    ]


def test_csv_mapping_groups_multiple_targets_per_source_path() -> None:
    content = """source_path,target_topic
data.batteryChargeLevelPercentage,carTelematics/battery/soc
data.batteryChargeLevelPercentage,homeassistant/polestar/soc
data.chargingStatusV2,carTelematics/battery/chargingStatus
data.batteryChargeLevelPercentage,carTelematics/battery/soc
"""

    assert parse_topic_mapping_csv(content) == {
        "data.batteryChargeLevelPercentage": (
            "carTelematics/battery/soc",
            "homeassistant/polestar/soc",
        ),
        "data.chargingStatusV2": (
            "carTelematics/battery/chargingStatus",
        ),
    }


@pytest.mark.parametrize("base_topic", ["polestar2", "polestar2/"])
def test_resolves_csv_targets_relative_to_base_or_explicitly_absolute(base_topic) -> None:
    content = """source_path,target_topic
data.batteryChargeLevelPercentage,carTelematics/battery/soc
data.batteryChargeLevelPercentage,absolute:homeassistant/polestar/soc
data.batteryChargeLevelPercentage,absolute:/leading/slash
data.chargingStatusV2,status/charging
"""
    mapping = parse_topic_mapping_csv(content)

    assert resolve_topic_mapping(mapping, base_topic) == {
        "data.batteryChargeLevelPercentage": (
            "polestar2/carTelematics/battery/soc",
            "homeassistant/polestar/soc",
            "/leading/slash",
        ),
        "data.chargingStatusV2": ("polestar2/status/charging",),
    }
    assert mapping == parse_topic_mapping_csv(content)


def test_deduplicates_equivalent_relative_and_absolute_targets() -> None:
    mapping = {"data.soc": ("soc", "absolute:polestar2/soc")}

    assert resolve_topic_mapping(mapping, "polestar2") == {
        "data.soc": ("polestar2/soc",),
    }


@pytest.mark.parametrize(
    ("base_topic", "target"),
    [("polestar2", "absolute:"), ("polestar2", "/soc"),
     ("", "soc"), ("/", "soc"), ("polestar2", "")],
)
def test_rejects_ambiguous_or_empty_mapping_targets(base_topic, target) -> None:
    with pytest.raises(TopicMappingError):
        resolve_topic_mapping({"data.soc": (target,)}, base_topic)


def test_resolves_empty_mapping() -> None:
    assert resolve_topic_mapping({}, "polestar2") == {}


def test_maps_dotted_json_source_to_additional_absolute_mqtt_target() -> None:
    mapping = parse_topic_mapping_csv(
        "source_path,target_topic\n"
        "carTelematics.battery.soc,absolute:openWB/LP1/SoC\n"
    )

    assert resolve_topic_mapping(mapping, "polestar2") == {
        "carTelematics.battery.soc": ("openWB/LP1/SoC",),
    }


@pytest.mark.parametrize(
    "source_path", ["", ".data.soc", "data..soc", "data.soc.", "data/soc"]
)
def test_rejects_empty_or_non_dotted_json_paths(source_path) -> None:
    with pytest.raises(TopicMappingError):
        parse_topic_mapping_csv(
            f"source_path,target_topic\n{source_path},absolute:openWB/LP1/SoC\n"
        )


def test_publishes_json_value_to_additional_targets_and_preserves_dynamic_topics() -> None:
    client = Mock()
    payload = {"carTelematics": {"battery": {"soc": 77, "charging": False}}}
    mapping = resolve_topic_mapping(parse_topic_mapping_csv(
        "source_path,target_topic\n"
        "carTelematics.battery.soc,absolute:openWB/LP1/SoC\n"
        "carTelematics.battery.soc,extra/soc\n"
    ), "polestar2")

    published = publish_json_topics(
        client, "polestar2/telemetry", payload, mapping=mapping,
    )

    assert client.publish.call_args_list == [
        call("polestar2/telemetry/carTelematics/battery/soc", "77", qos=1, retain=True),
        call("polestar2/telemetry/carTelematics/battery/charging", "false", qos=1, retain=True),
        call("openWB/LP1/SoC", "77", qos=1, retain=True),
        call("polestar2/extra/soc", "77", qos=1, retain=True),
    ]
    assert published == [entry.args[0] for entry in client.publish.call_args_list]


@pytest.mark.parametrize("value,payload", [(0, "0"), (False, "false"), ("", '""'),
                                          (None, "null"), (12.5, "12.5")])
def test_mapped_scalars_use_same_payload_as_dynamic_values(value, payload) -> None:
    client = Mock()

    publish_json_topics(
        client, "polestar2", {"data": {"soc": value}},
        mapping={"data.soc": ("extra/soc",)},
    )

    assert client.publish.call_args_list == [
        call("polestar2/data/soc", payload, qos=1, retain=True),
        call("extra/soc", payload, qos=1, retain=True),
    ]


@pytest.mark.parametrize("source", ["missing.soc", "data.missing", "data.soc.child",
                                   "data", "array", "polestar2.data.soc"])
def test_unavailable_or_non_scalar_source_does_not_suppress_dynamic_output(source) -> None:
    client = Mock()
    value = {"data": {"soc": 77}, "array": [1]}

    publish_json_topics(client, "polestar2", value, mapping={source: ("extra/soc",)})

    assert client.publish.call_args_list == [
        call("polestar2/data/soc", "77", qos=1, retain=True),
        call("polestar2/array/0", "1", qos=1, retain=True),
    ]


def test_mapping_cannot_overwrite_dynamic_topic() -> None:
    client = Mock()

    with pytest.raises(TopicMappingError, match="conflicts"):
        publish_json_topics(
            client, "polestar2", {"data": {"soc": 77, "other": 12}},
            mapping={"data.other": ("polestar2/data/soc",)},
        )

    client.publish.assert_not_called()


def test_missing_mapping_file_keeps_dynamic_output(tmp_path) -> None:
    client = Mock()
    mapping = load_topic_mapping(tmp_path / "missing.csv", "polestar2")

    publish_json_topics(client, "polestar2", {"soc": 77}, mapping=mapping)

    assert mapping == {}
    client.publish.assert_called_once_with("polestar2/soc", "77", qos=1, retain=True)


def test_loads_utf8_mapping_and_resolves_targets(tmp_path) -> None:
    path = tmp_path / "mapping.csv"
    path.write_text(
        "source_path,target_topic\n"
        "data.soc,extra/soc\n"
        "data.soc,absolute:openWB/LP1/SoC\n",
        encoding="utf-8-sig",
    )

    assert load_topic_mapping(path, "polestar2") == {
        "data.soc": ("polestar2/extra/soc", "openWB/LP1/SoC"),
    }


def test_header_only_mapping_is_valid(tmp_path) -> None:
    path = tmp_path / "mapping.csv"
    path.write_text("source_path,target_topic\n", encoding="utf-8")
    assert load_topic_mapping(path, "polestar2") == {}


@pytest.mark.parametrize("content", [
    "",
    "private-marker,target_topic\n",
    "source_path,target_topic\ndata.soc,target,private-marker\n",
    "source_path,target_topic\nprivate-marker\n",
    'source_path,target_topic\ndata.soc,"private-marker',
    "source_path,target_topic\ndata..private-marker,target\n",
    "source_path,target_topic\nprivate-marker,absolute:\n",
    "source_path,target_topic\nprivate-marker,/ambiguous\n",
])
def test_rejects_invalid_mapping_without_disclosing_content(tmp_path, content) -> None:
    path = tmp_path / "private-marker.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(TopicMappingError) as caught:
        load_topic_mapping(path, "polestar2")

    assert "private-marker" not in str(caught.value)
    assert "private-marker" not in "".join(traceback.format_exception(caught.value))


def test_invalid_utf8_is_reported_without_file_contents(tmp_path) -> None:
    path = tmp_path / "private-marker.csv"
    path.write_bytes(b"private-marker\xff")

    with pytest.raises(TopicMappingError, match="UTF-8") as caught:
        load_topic_mapping(path, "polestar2")

    assert "private-marker" not in "".join(traceback.format_exception(caught.value))


def test_unreadable_mapping_is_not_treated_as_missing(monkeypatch, tmp_path) -> None:
    def deny_read(*args, **kwargs):
        raise PermissionError("private-marker")

    monkeypatch.setattr(Path, "read_text", deny_read)
    path = tmp_path / "private-marker.csv"

    with pytest.raises(TopicMappingError, match="check access") as caught:
        load_topic_mapping(path, "polestar2")

    assert "private-marker" not in "".join(traceback.format_exception(caught.value))


def test_directory_is_not_treated_as_missing_mapping(tmp_path) -> None:
    with pytest.raises(TopicMappingError, match="file type"):
        load_topic_mapping(tmp_path, "polestar2")


def test_csv_error_reports_physical_line_after_blank_line() -> None:
    with pytest.raises(TopicMappingError, match="line 3"):
        parse_topic_mapping_csv("source_path,target_topic\n\ndata.soc,target,extra\n")


@pytest.mark.parametrize("path,value", [
    (r"data.a\.b", 10), (r"data.a\\b", 20), (r"data.a\/b", 30),
    (r"data.\e", 40), ("data.array.0.soc", 50), ("data.array.1.0", 60),
    ("data.0", 70), ("data.größe", 80),
])
def test_csv_paths_extract_special_keys_and_array_values(path, value) -> None:
    client = Mock()
    payload = {"data": {
        "a.b": 10, "a\\b": 20, "a/b": 30, "": 40,
        "array": [{"soc": 50}, [60]], "0": 70, "größe": 80,
    }}
    mapping = resolve_topic_mapping(parse_topic_mapping_csv(
        f"source_path,target_topic\n{path},absolute:extra/value\n"
    ), "polestar2")

    publish_json_topics(client, "polestar2", payload, mapping=mapping)

    client.publish.assert_any_call("extra/value", str(value), qos=1, retain=True)
    assert client.publish.call_count == 9


@pytest.mark.parametrize("path", [r"data.\q", "data.a\\", r"data.a\e",
                                  r"data.\ex", r"data.\e\e", "data..soc"])
def test_invalid_escapes_are_rejected_before_publishing(path) -> None:
    client = Mock()
    with pytest.raises(TopicMappingError):
        publish_json_topics(client, "polestar2", {"data": 1}, mapping={path: ("extra",)})
    client.publish.assert_not_called()


@pytest.mark.parametrize("index", ["1", "-1", "01", "٠", "999999999999999999999"])
def test_invalid_or_missing_array_index_does_not_publish_mapping(index) -> None:
    client = Mock()
    publish_json_topics(
        client, "polestar2", {"data": [50]}, mapping={f"data.{index}": ("extra",)},
    )
    client.publish.assert_called_once_with("polestar2/data/0", "50", qos=1, retain=True)


def test_escape_sequences_are_not_decoded_twice() -> None:
    assert parse_source_path(r"data.\\e") == ("data", "\\e")
    assert parse_source_path(r"data.\e") == ("data", "")


@pytest.mark.parametrize("topic", ["", "private-marker/+", "private-marker/#",
                                  "private-marker\0", "private-marker\ud800",
                                  "a" * 65536, "ä" * 32768])
def test_invalid_mapping_target_is_rejected_even_for_missing_source(topic) -> None:
    client = Mock()
    with pytest.raises(TopicMappingError) as caught:
        publish_json_topics(client, "valid", {"soc": 50}, mapping={"missing": (topic,)})
    client.publish.assert_not_called()
    assert "private-marker" not in str(caught.value)


@pytest.mark.parametrize("topic", ["/", "/leading", "trailing/", "double//level",
                                  "Größe space", "a" * 65535, "ä" * 32767 + "a"])
def test_valid_topic_names_and_utf8_byte_boundary(topic) -> None:
    validate_publish_topic(topic)


@pytest.mark.parametrize("root,payload", [
    ("invalid/+", {"soc": 50}),
    ("a" * 65534, {"x": 1}),
    ("root", {"fine": 1, "x" * 65535: 2}),
    ("root", {"fine": 1, "\ud800": 2}),
])
def test_invalid_dynamic_topic_prevents_all_publishes(root, payload) -> None:
    client = Mock()
    with pytest.raises(TopicMappingError):
        publish_json_topics(client, root, payload)
    client.publish.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"a": 1}, {"a": 1, "b": 1}])
def test_different_sources_cannot_share_target_even_if_missing_or_equal(payload) -> None:
    client = Mock()
    mapping = {"a": ("extra",), "b": ("extra",)}
    with pytest.raises(TopicMappingError, match="conflicts"):
        publish_json_topics(client, "root", payload, mapping=mapping)
    client.publish.assert_not_called()


def test_missing_source_cannot_claim_dynamic_topic() -> None:
    client = Mock()
    with pytest.raises(TopicMappingError, match="conflicts"):
        publish_json_topics(client, "root", {"soc": 1}, mapping={"missing": ("root/soc",)})
    client.publish.assert_not_called()


def test_duplicate_assignments_publish_once() -> None:
    client = Mock()
    publish_json_topics(client, "root", {"soc": 1}, mapping={"soc": ("extra", "extra")})
    assert client.publish.call_args_list == [
        call("root/soc", "1", qos=1, retain=True),
        call("extra", "1", qos=1, retain=True),
    ]


def test_relative_and_absolute_collision_is_rejected_during_resolution() -> None:
    with pytest.raises(TopicMappingError, match="conflicts"):
        resolve_topic_mapping({"a": ("soc",), "b": ("absolute:root/soc",)}, "root")
