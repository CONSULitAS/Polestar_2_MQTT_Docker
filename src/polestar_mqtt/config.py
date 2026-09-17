"""Application configuration boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from os import environ as process_environment
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


POLESTAR_CLIENT_ID_ENV = "POLESTAR_CLIENT_ID"
POLESTAR_CLIENT_SECRET_ENV = "POLESTAR_CLIENT_SECRET"
POLESTAR_CLIENT_SECRET_EXPIRES_AT_ENV = "POLESTAR_CLIENT_SECRET_EXPIRES_AT"
POLESTAR_ACCOUNT_ID_ENV = "POLESTAR_ACCOUNT_ID"
POLESTAR_VIN_ENV = "POLESTAR_VIN"
POLESTAR_API_BASE_URL_ENV = "POLESTAR_API_BASE_URL"

DEFAULT_POLESTAR_API_BASE_URL = (
    "https://pc-api.polestar.com/eu-north-1/data-portal/m2m"
)

DEFAULT_TIMEZONE = "Europe/Berlin"
DEFAULT_POLESTAR_CYCLE_SECONDS = 270
MIN_POLESTAR_CYCLE_SECONDS = 10
DEFAULT_MQTT_BROKER = "localhost"
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_KEEPALIVE_SECONDS = 60
DEFAULT_MQTT_BASE_TOPIC = "polestar2"
DEFAULT_MQTT_TOPIC_MAPPING_FILE = Path("/local-files/mqtt_topic_mapping.csv")
DEFAULT_MQTT_TOPIC_STATE_FILE = Path("/local-files/mqtt_topic_state.json")
DEFAULT_OPENWB_HOST = "localhost"
DEFAULT_OPENWB_PORT = 1883
DEFAULT_OPENWB_LP_NUM = 1

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
REDACTED_VALUE = "[REDACTED]"


class ConfigurationError(ValueError):
    """Raised when application configuration is missing or malformed."""


def redact_sensitive_text(text: str, *sensitive_values: str) -> str:
    """Replace known non-empty secrets in text intended for logs or errors."""

    redacted = text
    for value in sorted(set(sensitive_values), key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, REDACTED_VALUE)
    return redacted


def _parse_secret_expiry(value: str, timezone_name: str) -> datetime:
    """Convert the portal's YYYY-MM-DD value to midnight in local time."""

    try:
        if len(value) != 10:
            raise ValueError("unexpected date length")
        expiry_date = date.fromisoformat(value)
    except ValueError as error:
        raise ConfigurationError(
            f"{POLESTAR_CLIENT_SECRET_EXPIRES_AT_ENV} must use YYYY-MM-DD"
        ) from error

    try:
        configured_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ConfigurationError(
            f"TZ contains unknown timezone: {timezone_name}"
        ) from error

    local_expiry = datetime.combine(
        expiry_date,
        time.min,
        tzinfo=configured_timezone,
    )
    return local_expiry.astimezone(UTC)


@dataclass(frozen=True)
class DataPortalConfig:
    """Configuration required to authenticate with the Data Portal API."""

    client_id: str
    client_secret: str = field(repr=False)
    client_secret_expires_at: datetime
    account_id: str
    vin: str
    api_base_url: str
    timezone: str
    polestar_cycle: int
    mqtt_broker: str
    mqtt_port: int
    mqtt_keepalive: int
    mqtt_user: str
    mqtt_password: str = field(repr=False)
    mqtt_base_topic: str
    mqtt_topic_mapping_file: Path
    mqtt_topic_state_file: Path
    openwb_publish: bool
    openwb_host: str
    openwb_port: int
    openwb_lp_num: int

    def redact(self, text: str) -> str:
        """Redact every secret held by this configuration from text."""

        return redact_sensitive_text(text, self.client_secret, self.mqtt_password)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> DataPortalConfig:
        """Load Data Portal settings from an injectable environment mapping."""

        values = process_environment if environment is None else environment
        required_names = (
            POLESTAR_CLIENT_ID_ENV,
            POLESTAR_CLIENT_SECRET_ENV,
            POLESTAR_CLIENT_SECRET_EXPIRES_AT_ENV,
            POLESTAR_ACCOUNT_ID_ENV,
            POLESTAR_VIN_ENV,
        )
        required_values = {
            name: values.get(name, "").strip() for name in required_names
        }
        missing_names = [
            name for name, value in required_values.items() if not value
        ]
        if missing_names:
            raise ConfigurationError(
                "Required environment variables are missing or empty: "
                + ", ".join(missing_names)
            )

        client_id = required_values[POLESTAR_CLIENT_ID_ENV]
        client_secret = required_values[POLESTAR_CLIENT_SECRET_ENV]
        client_secret_expires_at = required_values[
            POLESTAR_CLIENT_SECRET_EXPIRES_AT_ENV
        ]
        account_id = required_values[POLESTAR_ACCOUNT_ID_ENV]
        vin = required_values[POLESTAR_VIN_ENV].upper()

        timezone = values.get("TZ", "").strip() or DEFAULT_TIMEZONE
        parsed_client_secret_expiry = _parse_secret_expiry(
            client_secret_expires_at,
            timezone,
        )
        if not VIN_PATTERN.fullmatch(vin):
            raise ConfigurationError(
                f"{POLESTAR_VIN_ENV} must be a valid 17-character VIN"
            )

        api_base_url = (
            values.get(POLESTAR_API_BASE_URL_ENV, "").strip()
            or DEFAULT_POLESTAR_API_BASE_URL
        )

        try:
            polestar_cycle = int(
                values.get("POLESTAR_CYCLE", str(DEFAULT_POLESTAR_CYCLE_SECONDS))
            )
        except ValueError as error:
            raise ConfigurationError("POLESTAR_CYCLE must be an integer") from error
        if polestar_cycle <= 0:
            raise ConfigurationError("POLESTAR_CYCLE must be greater than zero")
        if polestar_cycle < MIN_POLESTAR_CYCLE_SECONDS:
            raise ConfigurationError(
                "POLESTAR_CYCLE must be at least "
                f"{MIN_POLESTAR_CYCLE_SECONDS} seconds"
            )
        mqtt_broker = values.get("MQTT_BROKER", "").strip() or DEFAULT_MQTT_BROKER
        mqtt_port = int(values.get("MQTT_PORT", str(DEFAULT_MQTT_PORT)))
        mqtt_keepalive = int(
            values.get("MQTT_KEEPALIVE", str(DEFAULT_MQTT_KEEPALIVE_SECONDS))
        )
        mqtt_user = values.get("MQTT_USER", "")
        mqtt_password = values.get("MQTT_PASSWORD", "")
        mqtt_base_topic = (
            values.get("MQTT_BASE_TOPIC", "").strip() or DEFAULT_MQTT_BASE_TOPIC
        )
        mqtt_topic_mapping_file = Path(
            values.get("MQTT_TOPIC_MAPPING_FILE", "").strip()
            or DEFAULT_MQTT_TOPIC_MAPPING_FILE
        )
        openwb_publish = values.get("OPENWB_PUBLISH", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        openwb_host = (
            values.get("OPENWB_HOST", "").strip() or DEFAULT_OPENWB_HOST
        )
        openwb_port = int(values.get("OPENWB_PORT", str(DEFAULT_OPENWB_PORT)))
        openwb_lp_num = int(
            values.get("OPENWB_LP_NUM", str(DEFAULT_OPENWB_LP_NUM))
        )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            client_secret_expires_at=parsed_client_secret_expiry,
            account_id=account_id,
            vin=vin,
            api_base_url=api_base_url,
            timezone=timezone,
            polestar_cycle=polestar_cycle,
            mqtt_broker=mqtt_broker,
            mqtt_port=mqtt_port,
            mqtt_keepalive=mqtt_keepalive,
            mqtt_user=mqtt_user,
            mqtt_password=mqtt_password,
            mqtt_base_topic=mqtt_base_topic,
            mqtt_topic_mapping_file=mqtt_topic_mapping_file,
            mqtt_topic_state_file=Path(
                values.get("MQTT_TOPIC_STATE_FILE", "").strip() or DEFAULT_MQTT_TOPIC_STATE_FILE
            ),
            openwb_publish=openwb_publish,
            openwb_host=openwb_host,
            openwb_port=openwb_port,
            openwb_lp_num=openwb_lp_num,
        )
