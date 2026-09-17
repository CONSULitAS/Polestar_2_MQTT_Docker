"""Persist the topics from the last fully acknowledged publication."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from polestar_mqtt.publisher import validate_publish_topic


class TopicInventoryError(RuntimeError):
    """The local topic inventory could not be saved."""


def save_topic_inventory(path: Path, topics: list[str]) -> None:
    """Store topic names only, replacing the previous file after a complete write."""

    for topic in topics:
        validate_publish_topic(topic)
    content = json.dumps({"version": 1, "topics": sorted(set(topics))}, ensure_ascii=False)
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
