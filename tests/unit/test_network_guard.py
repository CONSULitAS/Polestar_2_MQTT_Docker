"""Tests for the mandatory offline unit-test environment."""

from __future__ import annotations

import socket

import pytest


def test_network_connections_are_blocked() -> None:
    with pytest.raises(RuntimeError, match="Network access is disabled"):
        socket.create_connection(("example.com", 443))

