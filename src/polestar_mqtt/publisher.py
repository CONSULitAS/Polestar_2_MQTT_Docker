"""MQTT and openWB publishing boundary.

Topic construction, MQTT lifecycle handling, and optional openWB forwarding
belong in this module. They are migrated from the legacy script in task M6.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Protocol, TypeAlias
from urllib.parse import quote


JsonScalar: TypeAlias = str | int | float | bool | None
TopicValue: TypeAlias = tuple[str, JsonScalar]
TopicMapping: TypeAlias = dict[str, tuple[str, ...]]
EMPTY_TOPIC_SEGMENT = "%EMPTY"
TOPIC_MAPPING_COLUMNS = ("source_path", "target_topic")
ABSOLUTE_TOPIC_PREFIX = "absolute:"


class TopicMappingError(ValueError):
    """Raised when CSV topic mapping content violates its contract."""


class MqttClient(Protocol):
    """Minimal MQTT client interface required by the publisher."""

    def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> object: ...


def validate_publish_topic(topic: str) -> None:
    """Validate MQTT Topic Name syntax without disclosing its contents."""

    if not isinstance(topic, str) or not topic or any(char in topic for char in "\0+#"):
        raise TopicMappingError("MQTT topic must be non-empty without NUL or wildcards")
    try:
        encoded = topic.encode("utf-8")
    except UnicodeError:
        raise TopicMappingError("MQTT topic must contain valid UTF-8") from None
    if len(encoded) > 65535:
        raise TopicMappingError("MQTT topic exceeds 65535 UTF-8 bytes")


def validate_mapping_targets(mapping: TopicMapping, dynamic_topics: set[str]) -> None:
    """Check every configured target even when its source is absent."""

    owners: dict[str, tuple[str, ...]] = {}
    for source_path, targets in mapping.items():
        source = parse_source_path(source_path)
        for topic in targets:
            validate_publish_topic(topic)
            if topic in dynamic_topics or (topic in owners and owners[topic] != source):
                raise TopicMappingError("Mapping target conflicts with another topic")
            owners[topic] = source


def normalize_topic_segment(segment: str) -> str:
    """Encode one JSON key as one deterministic MQTT-safe topic segment."""

    if not isinstance(segment, str):
        raise TypeError("MQTT topic segments must be strings")
    if not segment:
        return EMPTY_TOPIC_SEGMENT
    try:
        return quote(segment, safe="-._~", encoding="utf-8", errors="strict")
    except UnicodeError:
        raise TopicMappingError("JSON topic key must contain valid UTF-8") from None


def parse_source_path(source_path: str) -> tuple[str, ...]:
    """Decode dotted JSON keys; numeric segments address arrays by context."""

    segments: list[str] = []
    current: list[str] = []
    escaped = False
    empty_key = False
    for char in source_path:
        if escaped:
            if char == "e" and not current and not empty_key:
                empty_key = True
            elif char in ".\\/" and not empty_key:
                current.append(char)
            else:
                raise TopicMappingError("Invalid JSON path escape")
            escaped = False
        elif char == ".":
            if not current and not empty_key:
                raise TopicMappingError("JSON path contains an empty segment")
            segments.append("".join(current))
            current = []
            empty_key = False
        elif empty_key:
            raise TopicMappingError("Empty-key escape must occupy a whole segment")
        elif char == "\\":
            escaped = True
        elif char == "/":
            raise TopicMappingError("Slash in JSON key must be escaped")
        else:
            current.append(char)
    if escaped or (not current and not empty_key):
        raise TopicMappingError("JSON path is empty or incomplete")
    segments.append("".join(current))
    return tuple(segments)


def parse_topic_mapping_csv(content: str) -> TopicMapping:
    """Group dotted JSON source paths into ordered additional MQTT targets."""

    reader = csv.DictReader(StringIO(content), strict=True)
    grouped_targets: dict[str, list[str]] = {}
    try:
        if tuple(reader.fieldnames or ()) != TOPIC_MAPPING_COLUMNS:
            raise TopicMappingError(
                "CSV mapping header must be: source_path,target_topic"
            )

        for row in reader:
            source_path = (row.get("source_path") or "").strip()
            target_topic = (row.get("target_topic") or "").strip()
            if (
                None in row
                or any(value is None for value in row.values())
                or not source_path
                or not target_topic
                or target_topic == ABSOLUTE_TOPIC_PREFIX
                or target_topic.startswith("/")
            ):
                raise TopicMappingError(
                    f"Invalid CSV mapping entry on line {reader.line_num}: "
                    "expected a dotted JSON path and a non-empty relative "
                    "or absolute: target in exactly two columns"
                )
            try:
                parse_source_path(source_path)
            except TopicMappingError as error:
                raise TopicMappingError(
                    f"Invalid JSON source path on line {reader.line_num}: {error}"
                ) from None
            targets = grouped_targets.setdefault(source_path, [])
            if target_topic not in targets:
                targets.append(target_topic)
    except csv.Error:
        raise TopicMappingError(
            f"Malformed CSV mapping near line {reader.line_num}"
        ) from None

    return {
        source_path: tuple(targets)
        for source_path, targets in grouped_targets.items()
    }


def load_topic_mapping(path: Path, base_topic: str) -> TopicMapping:
    """Load optional UTF-8 CSV and resolve targets without exposing file contents."""

    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except UnicodeError:
        raise TopicMappingError("Mapping file must contain valid UTF-8") from None
    except OSError:
        raise TopicMappingError(
            "Mapping file could not be read; check access and file type"
        ) from None
    return resolve_topic_mapping(parse_topic_mapping_csv(content), base_topic)


def resolve_topic_mapping(mapping: TopicMapping, base_topic: str) -> TopicMapping:
    """Resolve MQTT targets while preserving the JSON source paths unchanged."""

    root_topic = base_topic.rstrip("/")
    resolved: TopicMapping = {}
    for source_path, targets in mapping.items():
        resolved_targets: list[str] = []
        for target in targets:
            if target.startswith(ABSOLUTE_TOPIC_PREFIX):
                topic = target[len(ABSOLUTE_TOPIC_PREFIX):]
                if not topic:
                    raise TopicMappingError("Absolute mapping target must not be empty")
            else:
                if not root_topic or not target or target.startswith("/"):
                    raise TopicMappingError(
                        "Relative mapping target requires a base and no leading slash"
                    )
                topic = f"{root_topic}/{target}"
            if topic not in resolved_targets:
                resolved_targets.append(topic)
        resolved[source_path] = tuple(resolved_targets)
    validate_mapping_targets(resolved, set())
    return resolved


def flatten_json_topics(root_topic: str, value: object) -> list[TopicValue]:
    """Flatten a JSON value into ordered MQTT topic and scalar pairs."""

    topics: list[TopicValue] = []

    def visit(topic: str, current: object) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise TypeError("JSON object keys must be strings")
                visit(f"{topic}/{normalize_topic_segment(key)}", child)
            return

        if isinstance(current, list):
            for index, child in enumerate(current):
                visit(f"{topic}/{index}", child)
            return

        if current is None or isinstance(current, (str, int, float, bool)):
            topics.append((topic, current))
            return

        raise TypeError(
            f"Unsupported JSON value type: {type(current).__name__}"
        )

    visit(root_topic.rstrip("/"), value)
    return topics


def serialize_json_scalar(value: JsonScalar) -> str:
    """Serialize one JSON scalar without creating an MQTT deletion payload."""

    if isinstance(value, str):
        return value if value else json.dumps(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def publish_json_topics(
    client: MqttClient,
    root_topic: str,
    value: object,
    *,
    mapping: TopicMapping | None = None,
) -> list[str]:
    """Publish dynamic leaves plus JSON values mapped to resolved MQTT targets."""

    topics = flatten_json_topics(root_topic, value)
    for topic, _ in topics:
        validate_publish_topic(topic)
    validate_mapping_targets(mapping or {}, {topic for topic, _ in topics})
    mapped_topics: set[str] = set()
    for source_path, targets in (mapping or {}).items():
        current = value
        for segment in parse_source_path(source_path):
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            elif (
                isinstance(current, list)
                and segment.isascii()
                and segment.isdecimal()
                and (segment == "0" or not segment.startswith("0"))
                and len(segment) <= len(str(len(current)))
                and int(segment) < len(current)
            ):
                current = current[int(segment)]
            else:
                break
        else:
            if isinstance(current, (dict, list)):
                continue
            if current is not None and not isinstance(current, (str, int, float, bool)):
                raise TopicMappingError("Mapped JSON value must be a scalar")
            for topic in dict.fromkeys(targets):
                if topic not in mapped_topics:
                    mapped_topics.add(topic)
                    topics.append((topic, current))

    published_topics: list[str] = []
    for topic, scalar in topics:
        client.publish(
            topic,
            serialize_json_scalar(scalar),
            qos=1,
            retain=True,
        )
        published_topics.append(topic)
    return published_topics
