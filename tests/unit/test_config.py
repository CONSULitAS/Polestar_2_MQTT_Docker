"""Unit tests for environment-based application configuration."""

from __future__ import annotations

from datetime import datetime

import pytest

from polestar_mqtt.config import (
    DEFAULT_MQTT_TOPIC_MAPPING_FILE,
    DEFAULT_POLESTAR_API_BASE_URL,
    REDACTED_VALUE,
    ConfigurationError,
    DataPortalConfig,
)


@pytest.fixture
def valid_environment() -> dict[str, str]:
    return {
        "POLESTAR_CLIENT_ID": "client-id",
        "POLESTAR_CLIENT_SECRET": "client-secret-value",
        "POLESTAR_CLIENT_SECRET_EXPIRES_AT": "2026-12-15",
        "POLESTAR_ACCOUNT_ID": "12345678-1234-1234-1234-123456789abc",
        "POLESTAR_VIN": "lpsvs000000000000",
    }


def test_loads_valid_configuration_with_defaults(
    valid_environment: dict[str, str],
) -> None:
    config = DataPortalConfig.from_environment(valid_environment)

    assert config.client_id == "client-id"
    assert config.client_secret == "client-secret-value"
    assert config.client_secret_expires_at == datetime.fromisoformat(
        "2026-12-14T23:00:00+00:00"
    )
    assert config.account_id == "12345678-1234-1234-1234-123456789abc"
    assert config.vin == "LPSVS000000000000"
    assert config.api_base_url == DEFAULT_POLESTAR_API_BASE_URL
    assert config.timezone == "Europe/Berlin"
    assert config.polestar_cycle == 270
    assert config.mqtt_broker == "localhost"
    assert config.mqtt_port == 1883
    assert config.mqtt_keepalive == 60
    assert config.mqtt_user == ""
    assert config.mqtt_password == ""
    assert config.mqtt_base_topic == "polestar2"
    assert config.mqtt_topic_mapping_file == DEFAULT_MQTT_TOPIC_MAPPING_FILE
    assert config.openwb_publish is False
    assert config.openwb_host == "localhost"
    assert config.openwb_port == 1883
    assert config.openwb_lp_num == 1


def test_loads_runtime_overrides(valid_environment: dict[str, str]) -> None:
    config = DataPortalConfig.from_environment(
        {
            **valid_environment,
            "POLESTAR_API_BASE_URL": "https://example.invalid/m2m",
            "TZ": "UTC",
            "POLESTAR_CYCLE": "300",
            "MQTT_BROKER": "mqtt.example.invalid",
            "MQTT_PORT": "8883",
            "MQTT_KEEPALIVE": "90",
            "MQTT_USER": "mqtt-user",
            "MQTT_PASSWORD": "mqtt-password-value",
            "MQTT_BASE_TOPIC": "vehicle",
            "MQTT_TOPIC_MAPPING_FILE": "local-files/custom-mapping.csv",
            "OPENWB_PUBLISH": "true",
            "OPENWB_HOST": "openwb.example.invalid",
            "OPENWB_PORT": "1884",
            "OPENWB_LP_NUM": "2",
        }
    )

    assert config.api_base_url == "https://example.invalid/m2m"
    assert config.client_secret_expires_at.isoformat() == "2026-12-15T00:00:00+00:00"
    assert config.polestar_cycle == 300
    assert (config.mqtt_broker, config.mqtt_port, config.mqtt_keepalive) == (
        "mqtt.example.invalid",
        8883,
        90,
    )
    assert (config.mqtt_user, config.mqtt_password, config.mqtt_base_topic) == (
        "mqtt-user",
        "mqtt-password-value",
        "vehicle",
    )
    assert config.mqtt_topic_mapping_file.as_posix() == (
        "local-files/custom-mapping.csv"
    )
    assert config.openwb_publish is True
    assert (config.openwb_host, config.openwb_port, config.openwb_lp_num) == (
        "openwb.example.invalid",
        1884,
        2,
    )


@pytest.mark.parametrize(
    ("portal_date", "timezone_name", "expected_utc"),
    [
        ("2026-12-15", "UTC", "2026-12-15T00:00:00+00:00"),
        ("2026-12-15", "Europe/Berlin", "2026-12-14T23:00:00+00:00"),
        ("2026-06-15", "Europe/Berlin", "2026-06-14T22:00:00+00:00"),
    ],
)
def test_interprets_portal_expiry_as_midnight_in_configured_timezone(
    valid_environment: dict[str, str],
    portal_date: str,
    timezone_name: str,
    expected_utc: str,
) -> None:
    config = DataPortalConfig.from_environment(
        {
            **valid_environment,
            "POLESTAR_CLIENT_SECRET_EXPIRES_AT": portal_date,
            "TZ": timezone_name,
        }
    )

    assert config.client_secret_expires_at.isoformat() == expected_utc


def test_reports_all_missing_required_values_without_secrets() -> None:
    with pytest.raises(ConfigurationError) as exception:
        DataPortalConfig.from_environment(
            {
                "POLESTAR_CLIENT_ID": " ",
                "POLESTAR_CLIENT_SECRET": "secret-must-not-leak",
            }
        )

    message = str(exception.value)
    assert "POLESTAR_CLIENT_ID" in message
    assert "POLESTAR_CLIENT_SECRET_EXPIRES_AT" in message
    assert "POLESTAR_ACCOUNT_ID" in message
    assert "POLESTAR_VIN" in message
    assert "secret-must-not-leak" not in message


@pytest.mark.parametrize(
    ("changes", "expected_message"),
    [
        ({"POLESTAR_VIN": "INVALID"}, "POLESTAR_VIN"),
        ({"POLESTAR_VIN": "LPSVS00000000000I"}, "POLESTAR_VIN"),
        ({"POLESTAR_CYCLE": "seconds"}, "POLESTAR_CYCLE must be an integer"),
        ({"POLESTAR_CYCLE": "0"}, "POLESTAR_CYCLE must be greater than zero"),
        ({"POLESTAR_CYCLE": "9"}, "POLESTAR_CYCLE must be at least 10 seconds"),
        (
            {"POLESTAR_CLIENT_SECRET_EXPIRES_AT": "15.12.2026"},
            "POLESTAR_CLIENT_SECRET_EXPIRES_AT must use YYYY-MM-DD",
        ),
        (
            {"POLESTAR_CLIENT_SECRET_EXPIRES_AT": "2026-12-15T00:00:00Z"},
            "POLESTAR_CLIENT_SECRET_EXPIRES_AT must use YYYY-MM-DD",
        ),
        ({"TZ": "Invalid/Timezone"}, "TZ contains unknown timezone"),
    ],
)
def test_rejects_invalid_configuration(
    valid_environment: dict[str, str],
    changes: dict[str, str],
    expected_message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=expected_message):
        DataPortalConfig.from_environment({**valid_environment, **changes})


def test_redacts_secrets_from_repr_and_text(
    valid_environment: dict[str, str],
) -> None:
    config = DataPortalConfig.from_environment(
        {**valid_environment, "MQTT_PASSWORD": "mqtt-password-value"}
    )

    representation = repr(config)
    assert config.client_secret not in representation
    assert config.mqtt_password not in representation
    assert "client_secret=" not in representation
    assert "mqtt_password=" not in representation
    assert config.redact(
        "client-secret-value and mqtt-password-value"
    ) == f"{REDACTED_VALUE} and {REDACTED_VALUE}"
