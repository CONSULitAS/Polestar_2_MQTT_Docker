"""One Data Portal read followed by confirmed MQTT publication."""

from __future__ import annotations

import json
from threading import Event
from time import monotonic

import paho.mqtt.client as mqtt

from polestar_mqtt.config import DataPortalConfig
from polestar_mqtt.polestar_api import DataPortalClient, DataPortalHttpClient, TokenProvider
from polestar_mqtt.publisher import load_topic_mapping, publish_json_topics, validate_publish_topic


MQTT_TIMEOUT_SECONDS = 30.0


class MqttRunError(RuntimeError):
    """A connection or publication could not be confirmed."""


class ConfirmedPublisher:
    """Wait for PUBACK within the total publication deadline."""

    def __init__(self, client: mqtt.Client) -> None:
        self.client = client
        self.deadline = monotonic() + MQTT_TIMEOUT_SECONDS

    def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> object:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise MqttRunError("MQTT publication deadline exceeded")
        result = self.client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MqttRunError("MQTT publish rejected")
        result.wait_for_publish(timeout=remaining)
        if not result.is_published():
            raise MqttRunError("MQTT publication was not acknowledged")
        return result


def run_once(config: DataPortalConfig) -> int:
    """Fetch one valid Battery snapshot and publish to the configured broker."""

    mapping = load_topic_mapping(config.mqtt_topic_mapping_file, config.mqtt_base_topic)
    root = f"{config.mqtt_base_topic.rstrip('/')}/telemetry/battery"
    validate_publish_topic(root)

    with DataPortalHttpClient(config.api_base_url) as http:
        provider = TokenProvider(http, config.client_id, config.client_secret)
        api = DataPortalClient(http, provider, config.account_id)
        api.ensure_vehicle_authorized(config.vin)
        battery = api.get_battery(config.vin)
        api.extract_soc(battery)
        api.extract_source_timestamp(battery)

    connected = Event()
    accepted = False

    def on_connect(client, userdata, flags, reason_code, properties):
        nonlocal accepted
        accepted = not reason_code.is_failure
        connected.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)
    client.connect_timeout = MQTT_TIMEOUT_SECONDS
    client.on_connect = on_connect
    if config.mqtt_user:
        client.username_pw_set(config.mqtt_user, config.mqtt_password)
    try:
        if client.connect(
            config.mqtt_broker, config.mqtt_port, config.mqtt_keepalive,
        ) != mqtt.MQTT_ERR_SUCCESS:
            raise MqttRunError("MQTT connection failed")
        if client.loop_start() != mqtt.MQTT_ERR_SUCCESS:
            raise MqttRunError("MQTT network loop failed")
        if not connected.wait(MQTT_TIMEOUT_SECONDS):
            raise MqttRunError("MQTT connection acknowledgement timed out")
        if not accepted:
            raise MqttRunError("MQTT connection rejected")
        topics = publish_json_topics(ConfirmedPublisher(client), root, battery, mapping=mapping)
        return len(topics)
    finally:
        try:
            client.disconnect()
        finally:
            client.loop_stop()


def main() -> int:
    """Return success only after every MQTT publication has been acknowledged."""

    try:
        config = DataPortalConfig.from_environment()
    except (ValueError, OverflowError):
        print("Data Portal runonce: invalid configuration")
        return 2
    try:
        count = run_once(config)
    except Exception as error:
        # Transport exceptions can contain credentials, URLs or response data.
        print(f"Data Portal runonce failed ({type(error).__name__})")
        return 1
    print(json.dumps({"data_portal": "successful", "mqtt": "acknowledged", "topics": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
