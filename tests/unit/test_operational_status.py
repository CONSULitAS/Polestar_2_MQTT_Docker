"""Operational status priority and credential expiry without network access."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from polestar_mqtt.operational_status import OperationalStatus


@pytest.mark.parametrize("days,expected", [
    (15, ""), (14, "credential_expiring"), (7, "credential_expiring"),
    (-1, "credential_expired"),
])
# Credential-Warnungen bleiben auch nach erfolgreichem Battery-Abruf erhalten.
def test_credential_warning_survives_success(days, expected):
    publisher = Mock()
    config = SimpleNamespace(
        mqtt_base_topic="test", client_secret_expires_at=(
            datetime.now(UTC) + timedelta(days=days, hours=1)),
    )
    status = OperationalStatus(publisher, config)
    status.start()
    status.result(battery_timestamp="2026-10-10T12:00:00Z")
    publisher.publish.assert_any_call(
        "test/container/last_error", expected, qos=1, retain=True,
    )


# Publikationsfehler haben Vorrang, ohne API- und Credential-Probleme zu verdecken.
def test_error_priority_preserves_active_causes():
    publisher = Mock()
    config = SimpleNamespace(
        mqtt_base_topic="test", client_secret_expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    status = OperationalStatus(publisher, config)
    status.result(failures={"endpoint": "DataPortalResponseError"}, source_time_unknown=True)
    status.failure(RuntimeError("private access token"))
    publisher.publish.assert_any_call(
        "test/container/last_error",
        "publication_failed;api_partial;credential_expiring;source_time_unknown",
        qos=1, retain=True,
    )
    publisher.publish.assert_any_call(
        "test/container/last_exception", "RuntimeError;DataPortalResponseError",
        qos=1, retain=True,
    )
    assert "private access token" not in str(publisher.mock_calls)
