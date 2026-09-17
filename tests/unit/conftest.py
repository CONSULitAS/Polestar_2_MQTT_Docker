"""Global safety guards for unit tests."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail every unit test that attempts to open a network connection."""

    def deny_network(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError(
            "Network access is disabled in unit tests; use requests-mock instead"
        )

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    yield

