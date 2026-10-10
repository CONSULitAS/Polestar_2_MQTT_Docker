"""Opt-in acceptance against a temporary loopback-only Mosquitto broker."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from threading import Event
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from polestar_mqtt.config import DataPortalConfig
from polestar_mqtt.openapi_catalog import build_endpoint_catalog, load_openapi_document
from polestar_mqtt.runonce import ConfirmedPublisher, run_once


pytestmark = pytest.mark.skipif(
    os.environ.get("POLESTAR_MQTT_INTEGRATION") != "1",
    reason="Set POLESTAR_MQTT_INTEGRATION=1 to start the isolated MQTT test broker",
)
VIN = "LPSVS000000000000"
BATTERY = "/v1/vehicles/{vin}/telemetry/battery"
ROOT = "integration-test/telemetry/battery"


class Broker:
    def __init__(self, directory):
        self.executable = shutil.which("mosquitto")
        if self.executable is None:
            pytest.fail("The explicit MQTT integration check requires mosquitto on PATH")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.configuration = directory / "mosquitto.conf"
        self.configuration.write_text(
            f"listener {self.port} 127.0.0.1\nallow_anonymous true\npersistence false\n"
        )
        self.process = None
        self.log = (directory / "mosquitto.log").open("w+")

    def start(self):
        self.process = subprocess.Popen(
            [self.executable, "-c", str(self.configuration)],
            stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                pytest.fail("Isolated MQTT broker exited during startup; inspect mosquitto.log")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        pytest.fail("Isolated MQTT broker startup timed out")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)


@pytest.fixture
def broker(tmp_path):
    instance = Broker(tmp_path)
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()
        instance.log.close()


@pytest.fixture
def scenario(broker, tmp_path, requests_mock):
    config = DataPortalConfig.from_environment({
        "POLESTAR_CLIENT_ID": "synthetic-client",
        "POLESTAR_CLIENT_SECRET": "synthetic-secret",
        "POLESTAR_CLIENT_SECRET_EXPIRES_AT": "2099-12-31",
        "POLESTAR_ACCOUNT_ID": "synthetic-account",
        "POLESTAR_VIN": VIN,
        "MQTT_BROKER": "127.0.0.1",
        "MQTT_PORT": str(broker.port),
        "MQTT_BASE_TOPIC": "integration-test",
        "MQTT_TOPIC_STATE_FILE": str(tmp_path / "state.json"),
        "MQTT_TOPIC_MAPPING_FILE": str(tmp_path / "mapping.csv"),
        "POLESTAR_OPENAPI_FILE": str(tmp_path / "missing-openapi.json"),
    })
    requests_mock.post(config.api_base_url + "/token", json={
        "accessToken": "synthetic-token", "expiresIn": 3600, "tokenType": "Bearer",
    })
    requests_mock.get(config.api_base_url + "/v1/vehicles", json={"data": [VIN]})
    for endpoint in build_endpoint_catalog(load_openapi_document(config.openapi_file)):
        requests_mock.get(config.api_base_url + endpoint.request_path(VIN), json={"data": {}})
    response = {
        "data": {"batteryChargeLevelPercentage": 50, "optional": 12, "nullable": 7,
                 "empty": ""},
        "meta": {"vin": VIN},
    }
    url = config.api_base_url + BATTERY.replace("{vin}", VIN)
    requests_mock.get(url, json=response)
    return config, response, url


@contextmanager
def connection(config, *, reconnect=False):
    connected = Event()
    accepted = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)

    def on_connect(client, userdata, flags, reason_code, properties):
        accepted.append(not reason_code.is_failure)
        connected.set()

    client.on_connect = on_connect
    try:
        assert client.connect(config.mqtt_broker, config.mqtt_port) == mqtt.MQTT_ERR_SUCCESS
        client.loop_start()
        assert connected.wait(10) and accepted[-1]
        if reconnect:
            client.disconnect()
            client.loop_stop()
            connected.clear()
            assert client.reconnect() == mqtt.MQTT_ERR_SUCCESS
            client.loop_start()
            assert connected.wait(10) and accepted[-1]
        yield client
    finally:
        client.disconnect()
        client.loop_stop()


def retained_snapshot(config, *, reconnect=False):
    received = {}
    finished = Event()
    subscribed = Event()
    with connection(config, reconnect=reconnect) as client:
        def on_subscribe(client, userdata, mid, reason_codes, properties):
            subscribed.set()

        def on_message(client, userdata, message):
            if message.topic == "integration-barrier":
                finished.set()
            elif message.retain:
                received[message.topic] = (message.payload, message.qos)

        client.on_subscribe = on_subscribe
        client.on_message = on_message
        assert client.subscribe("#", qos=1)[0] == mqtt.MQTT_ERR_SUCCESS
        assert subscribed.wait(10)
        # The same connection receives retained data before this later broker round trip.
        ConfirmedPublisher(client).publish("integration-barrier", "done", qos=1, retain=False)
        assert finished.wait(10)
    return received


# Echte retained Werte, Löschungen und geschützte/fremde Topics werden getrennt geprüft.
def test_retained_cleanup_preserves_status_and_foreign_topics(scenario, requests_mock):
    config, response, url = scenario
    preserved = {
        "integration-test/container/connected": "online",
        "integration-test/container/credentials/status": "ok",
        "integration-test/charging/removed/log/state": "historic",
        "foreign/status": "untouched",
    }
    with connection(config) as client:
        publisher = ConfirmedPublisher(client)
        for topic, payload in preserved.items():
            publisher.publish(topic, payload, qos=1, retain=True)
    config.mqtt_topic_mapping_file.write_text(
        "source_path,target_topic\ndata.optional,absolute:integration-mapped/optional\n"
    )
    assert run_once(config)[1] == 0
    first = retained_snapshot(config)
    assert first[ROOT + "/data/optional"] == (b"12", 1)
    assert first["integration-mapped/optional"] == (b"12", 1)
    assert first[ROOT + "/data/empty"] == (b'""', 1)
    assert first[ROOT + "/log/state"] == (b"OK", 1)

    del response["data"]["optional"]
    response["data"]["nullable"] = None
    requests_mock.get(url, json=response)
    config.mqtt_topic_mapping_file.write_text("source_path,target_topic\n")
    assert run_once(config)[1] == 0
    current = retained_snapshot(config, reconnect=True)
    assert ROOT + "/data/optional" not in current
    assert "integration-mapped/optional" not in current
    assert current[ROOT + "/data/nullable"] == (b"null", 1)
    assert current[ROOT + "/data/batteryChargeLevelPercentage"] == (b"50", 1)
    assert current[ROOT + "/log/state"] == (b"OK", 1)
    assert current[ROOT + "/log/timestamp"][0].endswith(b"Z")
    preserved["integration-test/container/connected"] = "offline"
    for topic, payload in preserved.items():
        assert current[topic] == (payload.encode(), 1)
    state = json.loads(config.mqtt_topic_state_file.read_text())
    assert state["pending"] == {} and state["intended"] == {}


# Ein Broker ohne retained Bestand erhält unveränderte Werte beim nächsten Einmallauf erneut.
def test_broker_restart_republishes_unchanged_values(scenario, broker):
    config, _, _ = scenario
    assert run_once(config)[1] == 0
    before = retained_snapshot(config)
    inventory_before = config.mqtt_topic_state_file.read_bytes()
    broker.stop()
    broker.start()
    assert retained_snapshot(config) == {}
    assert run_once(config)[1] == 0
    after = retained_snapshot(config)
    assert set(after) == set(before)
    for topic, payload in before.items():
        if not topic.endswith(("/log/timestamp", "/container/last_update")):
            assert after[topic] == payload
    assert config.mqtt_topic_state_file.read_bytes() == inventory_before


# Ein NoData-Endpunkt behält reale retained Werte und sein Inventar bis zur Erholung.
def test_endpoint_failure_preserves_retained_values(scenario, requests_mock):
    config, _, _ = scenario
    endpoint = "/v1/vehicles/{vin}/telemetry/exterior"
    url = config.api_base_url + endpoint.replace("{vin}", VIN)
    topic = "integration-test/telemetry/exterior/data/value"
    requests_mock.get(url, json={"data": {"value": 17}})
    assert run_once(config)[1] == 0
    requests_mock.get(url, status_code=404, json={"error": {
        "code": "DATA_NOT_AVAILABLE", "message": "No exterior data is available for this vehicle.",
    }})
    assert run_once(config)[1] == 1
    assert retained_snapshot(config)[topic] == (b"17", 1)
    requests_mock.get(url, json={"data": {}})
    assert run_once(config)[1] == 0
    after = retained_snapshot(config)
    assert topic not in after
    assert after["integration-test/telemetry/exterior/log/state"] == (b"OK", 1)



# Der Broker veröffentlicht das konfigurierte Offline-LWT nach einem echten Prozessabbruch.
def test_broker_publishes_last_will_after_process_exit(scenario):
    config, _, _ = scenario
    worker = """
import sys
from threading import Event
import paho.mqtt.client as mqtt
from polestar_mqtt.operational_status import configure_last_will
from polestar_mqtt.runonce import ConfirmedPublisher
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)
configure_last_will(client, 'integration-test')
connected = Event()
client.on_connect = lambda *args: connected.set()
client.connect('127.0.0.1', int(sys.argv[1]))
client.loop_start()
assert connected.wait(10)
ConfirmedPublisher(client).publish(
    'integration-test/container/connected', 'online', qos=1, retain=True)
print('ready', flush=True)
Event().wait()
"""
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", worker, str(config.mqtt_port)],
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        assert retained_snapshot(config)["integration-test/container/connected"] == (b"online", 1)
        process.kill()
        process.wait(timeout=10)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observed = retained_snapshot(config).get("integration-test/container/connected")
            if observed == (b"offline", 1):
                break
            time.sleep(0.05)
        else:
            pytest.fail("Broker did not publish the offline last will")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()
