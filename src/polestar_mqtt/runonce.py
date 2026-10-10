"""One Data Portal read followed by confirmed MQTT publication."""

from __future__ import annotations

import json
from threading import Event
from time import monotonic

import paho.mqtt.client as mqtt

from polestar_mqtt.config import ConfigurationError, DataPortalConfig
from polestar_mqtt.openapi_catalog import (
    aggregate_scopes, build_endpoint_catalog, load_openapi_document,
)
from polestar_mqtt.polestar_api import (
    DataPortalClient, DataPortalHttpClient, DataPortalResponseError, TokenProvider,
)
from polestar_mqtt.publisher import (
    TopicMappingError, flatten_json_topics, load_topic_mapping, publish_json_topics,
    validate_mapping_targets, validate_publish_topic,
)

from polestar_mqtt.topic_inventory import load_topic_inventory, save_topic_inventory


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


def run_once(config: DataPortalConfig) -> tuple[int, int]:
    """Fetch all endpoints and publish successful responses to the broker."""

    catalog = build_endpoint_catalog(load_openapi_document(config.openapi_file))
    scope = aggregate_scopes(catalog)
    mapping = load_topic_mapping(config.mqtt_topic_mapping_file, config.mqtt_base_topic)
    inventory, unassigned_topics = load_topic_inventory(config.mqtt_topic_state_file)
    battery_path = "/v1/vehicles/{vin}/telemetry/battery"

    with DataPortalHttpClient(config.api_base_url) as http:
        provider = TokenProvider(http, config.client_id, config.client_secret, scope=scope)
        api = DataPortalClient(http, provider, config.account_id)
        api.ensure_vehicle_authorized(config.vin)
        responses, failures = api.get_catalog(catalog, config.vin)
        battery = responses.get(battery_path)
        if battery is not None:
            try:
                api.extract_soc(battery)
                api.validate_response_vin(battery, config.vin)
                api.extract_source_timestamp(battery)
            except DataPortalResponseError:
                failures[battery_path] = "DataPortalResponseError"
                del responses[battery_path]

    publications = []
    dynamic_topics = set()
    for endpoint in catalog:
        if endpoint.path_template not in responses:
            continue
        root = config.mqtt_base_topic.rstrip("/") + endpoint.topic_root
        validate_publish_topic(root)
        payload = responses[endpoint.path_template]
        for topic, _ in flatten_json_topics(root, payload):
            validate_publish_topic(topic)
            if topic in dynamic_topics:
                raise TopicMappingError("Dynamic endpoint topics overlap")
            dynamic_topics.add(topic)
        endpoint_mapping = mapping if endpoint.path_template == battery_path else {}
        publications.append((endpoint.path_template, root, payload, endpoint_mapping))
    validate_mapping_targets(mapping, dynamic_topics)
    if not dynamic_topics:
        raise DataPortalResponseError("No publishable endpoint data is available")

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
        publisher = ConfirmedPublisher(client)
        topics = []
        for endpoint_path, root, payload, endpoint_mapping in publications:
            confirmed = publish_json_topics(publisher, root, payload, mapping=endpoint_mapping)
            topics.extend(confirmed)
            if sorted(set(confirmed)) == inventory.get(endpoint_path, []):
                continue
            inventory[endpoint_path] = confirmed
            save_topic_inventory(
                config.mqtt_topic_state_file, inventory, unassigned_topics=unassigned_topics,
            )
        return len(topics), len(failures)
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
        count, failed_endpoints = run_once(config)
    except ConfigurationError:
        print("Data Portal runonce: invalid file configuration")
        return 2
    except Exception as error:
        # Transport exceptions can contain credentials, URLs or response data.
        print(f"Data Portal runonce failed ({type(error).__name__})")
        return 1
    summary = {
        "data_portal": "partial" if failed_endpoints else "successful",
        "mqtt": "acknowledged", "topics": count,
    }
    if failed_endpoints:
        summary["failed_endpoints"] = failed_endpoints
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
