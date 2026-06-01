import pytest
from unittest.mock import Mock

import Polestar_2_MQTT as app

#####################################
# tests for API response handling


def test_get_car_data_returns_matching_vin(monkeypatch, make_response):
    car_payload = {
        "data": {
            "getConsumerCarsV2": [
                {"vin": "OTHER", "modelName": "Ignore me"},
                {"vin": "VIN123", "modelName": "Polestar 2"},
            ]
        }
    }

    monkeypatch.setattr(
        app.requests,
        "post",
        lambda url, headers=None, json=None: make_response(status_code=200, json_data=car_payload),
    )

    result = app.get_car_data("VIN123", "token-123")

    assert result == {"vin": "VIN123", "modelName": "Polestar 2"}


def test_get_car_data_raises_value_error_when_vin_is_missing(monkeypatch, make_response):
    monkeypatch.setattr(
        app.requests,
        "post",
        lambda url, headers=None, json=None: make_response(
            status_code=200,
            json_data={"data": {"getConsumerCarsV2": [{"vin": "OTHER"}]}},
        ),
    )

    with pytest.raises(ValueError, match="no data for car with VIN VIN123"):
        app.get_car_data("VIN123", "token-123")


def test_get_car_data_calls_publish_error_and_raise_for_unexpected_shape(
    monkeypatch,
    make_response,
):
    monkeypatch.setattr(
        app.requests,
        "post",
        lambda url, headers=None, json=None: make_response(
            status_code=200,
            json_data={"data": {"getConsumerCarsV2": {"vin": "VIN123"}}},
        ),
    )

    def fake_publish_error_and_raise(message, exception):
        raise RuntimeError(f"{message} | {exception}")

    monkeypatch.setattr(app, "publish_error_and_raise", fake_publish_error_and_raise)

    with pytest.raises(RuntimeError, match="unexpected API response"):
        app.get_car_data("VIN123", "token-123")


def test_get_car_telemetry_data_returns_api_data(monkeypatch, make_response):
    telemetry_payload = {
        "data": {
            "carTelematicsV2": {
                "battery": {"batteryChargeLevelPercentage": 77},
                "odometer": {"odometerMeters": 123456},
            }
        }
    }

    monkeypatch.setattr(
        app.requests,
        "post",
        lambda url, headers=None, json=None: make_response(
            status_code=200,
            json_data=telemetry_payload,
        ),
    )

    result = app.get_car_telemetry_data("VIN123", "token-123")

    assert result == telemetry_payload["data"]["carTelematicsV2"]


def test_get_car_telemetry_data_calls_publish_error_and_raise_on_http_error(
    monkeypatch,
    make_response,
):
    monkeypatch.setattr(
        app.requests,
        "post",
        lambda url, headers=None, json=None: make_response(
            status_code=500,
            json_data={"error": "backend unavailable"},
        ),
    )

    def fake_publish_error_and_raise(message, exception):
        raise RuntimeError(f"{message} | {exception}")

    monkeypatch.setattr(app, "publish_error_and_raise", fake_publish_error_and_raise)

    with pytest.raises(RuntimeError, match="no data received"):
        app.get_car_telemetry_data("VIN123", "token-123")


def test_parse_runtime_args_supports_runonce():
    args = app.parse_runtime_args(["runonce"])

    assert args.mode == "runonce"

#####################################
# tests for run-once main flow


def test_main_runonce_completes_single_cycle_and_shuts_down(monkeypatch):
    fake_client = Mock()

    monkeypatch.setattr(app, "client", fake_client)
    monkeypatch.setattr(app, "OPENWB_PUBLISH", False)
    monkeypatch.setattr(app.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "mqtt_connect", lambda: None)
    monkeypatch.setattr(
        app.auth_client,
        "ensure_valid_token",
        lambda access_token, expiry_time, refresh_token, email, password: (
            "token-123",
            "expiry-marker",
            "refresh-123",
        ),
    )
    monkeypatch.setattr(
        app,
        "get_car_data",
        lambda vin, access_token: {"vin": vin, "modelName": "P2"},
    )
    monkeypatch.setattr(
        app,
        "get_car_telemetry_data",
        lambda vin, access_token: {"battery": {"batteryChargeLevelPercentage": 80}},
    )
    monkeypatch.setattr(app, "publish_json_as_mqtt", lambda topic, payload: None)
    monkeypatch.setattr(app, "shutdown_clients", lambda: fake_client.publish("shutdown", "done"))

    app.main(run_once=True)

    published_topics = [call.args[0] for call in fake_client.publish.call_args_list]
    assert app.MQTT_TIMESTAMP_TOPIC in published_topics
    assert "shutdown" in published_topics
