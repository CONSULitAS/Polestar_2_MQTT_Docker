"""Persist confirmed topic names per endpoint without storing measurement values."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from polestar_mqtt.openapi_catalog import ENDPOINT_PATH_PATTERN
from polestar_mqtt.publisher import validate_publish_topic


class TopicInventoryError(RuntimeError):
    """The local topic inventory could not be read or saved safely."""


def _topic_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TopicInventoryError("Topic inventory requires topic lists")
    try:
        for topic in value:
            validate_publish_topic(topic)
    except (TypeError, ValueError):
        raise TopicInventoryError("Topic inventory contains invalid topics") from None
    return sorted(set(value))


def _endpoint_topics(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise TopicInventoryError("Topic inventory requires endpoint entries")
    result = {}
    for endpoint, topics in value.items():
        if not isinstance(endpoint, str) or not ENDPOINT_PATH_PATTERN.fullmatch(endpoint):
            raise TopicInventoryError("Topic inventory contains an invalid endpoint")
        result[endpoint] = _topic_list(topics)
    return result


def load_topic_inventory(path: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Load endpoint history; retain unassignable version-1 topics separately."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, []
    except (OSError, ValueError):
        raise TopicInventoryError("Topic inventory could not be read") from None
    if not isinstance(payload, dict) or type(payload.get("version")) is not int:
        raise TopicInventoryError("Topic inventory has an invalid format")
    if payload["version"] == 1 and set(payload) == {"version", "topics"}:
        return {}, _topic_list(payload["topics"])
    if payload["version"] != 2 or set(payload) != {"version", "endpoints", "unassigned_topics"}:
        raise TopicInventoryError("Topic inventory has an unsupported format")
    return _endpoint_topics(payload["endpoints"]), _topic_list(payload["unassigned_topics"])


def save_topic_inventory(
    path: Path, endpoints: dict[str, list[str]], *, unassigned_topics: list[str] | None = None,
) -> None:
    """Atomically store confirmed endpoint history and unassigned legacy topics."""

    content = json.dumps({
        "version": 2,
        "endpoints": _endpoint_topics(endpoints),
        "unassigned_topics": _topic_list(
            unassigned_topics if unassigned_topics is not None else [],
        ),
    }, ensure_ascii=False, sort_keys=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary_path = Path(file.name)
            file.write(content + "\n")
        temporary_path.replace(path)
    except OSError:
        raise TopicInventoryError(
            "Topic inventory could not be saved; check directory access"
        ) from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                raise TopicInventoryError("Temporary inventory file could not be removed") from None
