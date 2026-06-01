from unittest.mock import Mock, call

import Polestar_2_MQTT as app

#####################################
# tests for MQTT publishers and shutdown


def test_publish_json_as_mqtt_flattens_nested_structures(monkeypatch):
    fake_client = Mock()
    monkeypatch.setattr(app, "client", fake_client)

    payload = {
        "battery": {
            "batteryChargeLevelPercentage": 78,
            "chargingStatus": "Charging",
        },
        "health": [{"daysToService": 42}],
    }

    app.publish_json_as_mqtt("polestar2/root", payload)

    fake_client.publish.assert_has_calls(
        [
            call(
                "polestar2/root/battery/batteryChargeLevelPercentage",
                "78",
                qos=1,
                retain=True,
            ),
            call(
                "polestar2/root/battery/chargingStatus",
                "Charging",
                qos=1,
                retain=True,
            ),
            call(
                "polestar2/root/health/0/daysToService",
                "42",
                qos=1,
                retain=True,
            ),
        ],
        any_order=False,
    )


def test_publish_soc_to_openwb_uses_configured_topic(monkeypatch):
    fake_client = Mock()
    monkeypatch.setattr(app, "client_openwb", fake_client, raising=False)
    monkeypatch.setattr(app, "OPENWB_TOPIC", "openWB/set/lp/1/%Soc", raising=False)

    app.publish_soc_to_openwb({"batteryChargeLevelPercentage": 64})

    fake_client.publish.assert_called_once_with("openWB/set/lp/1/%Soc", 64, qos=1, retain=True)


def test_shutdown_clients_disconnects_main_client(monkeypatch):
    fake_client = Mock()
    monkeypatch.setattr(app, "client", fake_client)
    monkeypatch.setattr(app, "OPENWB_PUBLISH", False)

    app.shutdown_clients()

    fake_client.disconnect.assert_called_once_with()
    fake_client.loop_stop.assert_called_once_with()
