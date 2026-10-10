"""One Data Portal read followed by confirmed MQTT publication."""

from __future__ import annotations

import json
import socket
from threading import Event
from time import monotonic

import paho.mqtt.client as mqtt

from polestar_mqtt.config import ConfigurationError, DataPortalConfig
from polestar_mqtt.openapi_catalog import (
    aggregate_scopes, build_endpoint_catalog, load_openapi_document,
)
from polestar_mqtt.operational_status import OperationalStatus, configure_last_will
from polestar_mqtt.polestar_api import (
    DataPortalClient, DataPortalHttpClient, DataPortalResponseError, TokenProvider,
    local_error_state,
)
from polestar_mqtt.publisher import (
    TopicMappingError, flatten_json_topics, load_topic_mapping, prepare_json_topics,
    serialize_json_scalar, validate_mapping_targets, validate_publish_topic,
)

from polestar_mqtt.topic_inventory import ManagedTopicInventory


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

    with ManagedTopicInventory(config) as inventory:
        return _run_once(config, inventory)


def _run_once(config: DataPortalConfig, inventory: ManagedTopicInventory) -> tuple[int, int]:
    catalog = build_endpoint_catalog(load_openapi_document(config.openapi_file))
    scope = aggregate_scopes(catalog)
    mapping = load_topic_mapping(config.mqtt_topic_mapping_file, config.mqtt_base_topic)
    battery_path = "/v1/vehicles/{vin}/telemetry/battery"

    responses, failures = {}, {}
    fatal_error = None
    battery_timestamp = None
    source_time_unknown = False
    endpoint_logs = {}
    try:
        with DataPortalHttpClient(config.api_base_url) as http:
            provider = TokenProvider(http, config.client_id, config.client_secret, scope=scope)
            api = DataPortalClient(http, provider, config.account_id)
            api.ensure_vehicle_authorized(config.vin)
            responses, failures = api.get_catalog(catalog, config.vin)
            for endpoint_path, payload in list(responses.items()):
                try:
                    if not isinstance(payload.get("data"), dict):
                        raise DataPortalResponseError("Endpoint response contains no data object")
                    meta = payload.get("meta", {})
                    if not isinstance(meta, dict):
                        raise DataPortalResponseError("Endpoint response contains invalid metadata")
                    for section in (payload["data"], meta):
                        vin = section.get("vin")
                        if vin is not None and (
                            not isinstance(vin, str) or vin.strip().upper() != config.vin
                        ):
                            raise DataPortalResponseError("Endpoint response VIN does not match")
                    api.extract_source_timestamp(payload)
                    if endpoint_path == battery_path:
                        api.extract_soc(payload)
                        api.validate_response_vin(payload, config.vin)
                except DataPortalResponseError as error:
                    failures[endpoint_path] = "DataPortalResponseError"
                    _, timestamp = api.endpoint_logs[endpoint_path]
                    api.endpoint_logs[endpoint_path] = (local_error_state(error), timestamp)
                    del responses[endpoint_path]
            endpoint_logs = api.endpoint_logs
            if battery_path in responses:
                battery_timestamp = endpoint_logs[battery_path][1]
                source_time_unknown = api.extract_source_timestamp(responses[battery_path]) is None
    except Exception as error:
        fatal_error = error
        responses, failures = {}, {}

    publications = []
    dynamic_topics = set()
    log_roots = {
        config.mqtt_base_topic.rstrip("/") + endpoint.topic_root + "/log"
        for endpoint in catalog
    }

    def validate_telemetry_topic(topic: str) -> None:
        inventory.validate_topic(topic)
        if any(topic == root or topic.startswith(root + "/") for root in log_roots):
            raise TopicMappingError("Telemetry target overlaps endpoint log namespace")

    for targets in mapping.values():
        for topic in targets:
            validate_telemetry_topic(topic)
    for endpoint in catalog:
        if endpoint.path_template not in responses:
            continue
        root = config.mqtt_base_topic.rstrip("/") + endpoint.topic_root
        validate_publish_topic(root)
        payload = responses[endpoint.path_template]
        for topic, _ in flatten_json_topics(root, payload):
            validate_telemetry_topic(topic)
            if topic in dynamic_topics:
                raise TopicMappingError("Dynamic endpoint topics overlap")
            dynamic_topics.add(topic)
        endpoint_mapping = mapping if endpoint.path_template == battery_path else {}
        planned = prepare_json_topics(root, payload, mapping=endpoint_mapping)
        publications.append((endpoint.path_template, planned))
    validate_mapping_targets(mapping, dynamic_topics)
    inventory.validate_plan({
        endpoint: [topic for topic, _ in planned] for endpoint, planned in publications
    })
    log_publications = []
    for endpoint in catalog:
        if endpoint.path_template not in endpoint_logs:
            continue
        root = config.mqtt_base_topic.rstrip("/") + endpoint.topic_root + "/log"
        state, timestamp = endpoint_logs[endpoint.path_template]
        for name, value in (("state", state), ("timestamp", timestamp)):
            topic = root + "/" + name
            validate_publish_topic(topic)
            log_publications.append((topic, value))

    connected = Event()
    accepted = False

    def on_connect(client, userdata, flags, reason_code, properties):
        nonlocal accepted
        accepted = not reason_code.is_failure
        connected.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)
    configure_last_will(client, config.mqtt_base_topic)
    client.connect_timeout = MQTT_TIMEOUT_SECONDS
    client.on_connect = on_connect
    if config.mqtt_user:
        client.username_pw_set(config.mqtt_user, config.mqtt_password)
    status = None
    primary_error = None
    graceful_disconnect = True
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
        status = OperationalStatus(publisher, config)
        status.start()
        status.result(battery_timestamp=battery_timestamp, failures=failures,
                      fatal_error=fatal_error, source_time_unknown=source_time_unknown)
        if fatal_error is not None:
            raise fatal_error
        topics = []
        for topic, value in log_publications:
            publisher.publish(topic, value, qos=1, retain=True)
            topics.append(topic)
        for endpoint_path, planned in publications:
            desired = [topic for topic, _ in planned]
            changed = (sorted(desired) != inventory.endpoints.get(endpoint_path, [])
                       or endpoint_path in inventory.pending)
            obsolete = inventory.begin(endpoint_path, desired) if changed else []
            for topic, value in planned:
                publisher.publish(topic, serialize_json_scalar(value), qos=1, retain=True)
                topics.append(topic)
            for topic in obsolete:
                publisher.publish(topic, "", qos=1, retain=True)
                topics.append(topic)
            if changed:
                inventory.finish(endpoint_path, desired)
        if not dynamic_topics:
            raise DataPortalResponseError("No publishable endpoint data is available")
        return len(topics) + status.count + 1, len(failures)
    except Exception as error:
        primary_error = error
        if (status is not None and fatal_error is None
                and not isinstance(error, DataPortalResponseError)):
            try:
                status.failure(error)
            except Exception:
                pass
        raise
    finally:
        try:
            if status is not None:
                try:
                    status.stop()
                except Exception:
                    graceful_disconnect = False
                    if primary_error is None:
                        raise
        finally:
            try:
                if graceful_disconnect:
                    client.disconnect()
                else:
                    # A normal DISCONNECT would cancel the offline will after a failed publish.
                    connection = client.socket()
                    if connection is not None:
                        try:
                            connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
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
