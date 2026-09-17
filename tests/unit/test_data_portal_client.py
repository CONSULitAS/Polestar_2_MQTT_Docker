"""Unit tests for Data Portal vehicle and Battery response handling."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import requests
import requests_mock as requests_mock_module

from polestar_mqtt.polestar_api import (
    AccessToken,
    DataPortalAuthenticationError,
    DataPortalBadRequestError,
    DataPortalClient,
    DataPortalForbiddenError,
    DataPortalHttpClient,
    DataPortalNotFoundError,
    DataPortalRateLimitError,
    DataPortalRequestError,
    DataPortalResponseError,
    DataPortalServerError,
    DataPortalServiceUnavailableError,
    VehicleNotAuthorizedError,
)


BASE_URL = "https://example.invalid/m2m"
VIN = "LPSVS000000000000"
BATTERY_URL = f"{BASE_URL}/v1/vehicles/{VIN}/telemetry/battery"


class FakeTokenProvider:
    def __init__(self) -> None:
        self.force_refresh_calls: list[bool] = []

    def get_token(self, *, force_refresh: bool = False) -> AccessToken:
        self.force_refresh_calls.append(force_refresh)
        value = "renewed-token" if force_refresh else "cached-token"
        return AccessToken(value, "Bearer", 3600.0, 4600.0)


def make_client(
    token_provider: FakeTokenProvider | None = None,
    **kwargs,
) -> tuple[DataPortalClient, FakeTokenProvider]:
    provider = token_provider or FakeTokenProvider()
    client = DataPortalClient(
        DataPortalHttpClient(BASE_URL),
        provider,  # type: ignore[arg-type]
        "account-id",
        **kwargs,
    )
    return client, provider


def battery_payload(**data_overrides: object) -> dict[str, object]:
    return {
        "data": {
            "vin": VIN,
            "batteryChargeLevelPercentage": 77,
            **data_overrides,
        },
        "meta": {"vin": VIN, "domain": "battery"},
    }


def test_builds_required_authorization_headers() -> None:
    client, _ = make_client()

    assert client.authorization_headers() == {
        "Accept": "application/json",
        "Authorization": "Bearer cached-token",
        "x-client-id": "account-id",
    }


def test_lists_vehicles_and_authorizes_vin_case_insensitively(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(f"{BASE_URL}/v1/vehicles", json={"data": [VIN.lower()]})
    client, _ = make_client()

    client.ensure_vehicle_authorized(VIN)

    assert requests_mock.last_request.headers["Authorization"] == "Bearer cached-token"


def test_rejects_vin_missing_from_authorized_vehicles(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(f"{BASE_URL}/v1/vehicles", json={"data": []})
    client, _ = make_client()

    with pytest.raises(VehicleNotAuthorizedError):
        client.ensure_vehicle_authorized(VIN)


@pytest.mark.parametrize("payload", [None, [], {}, {"data": None}, {"data": [""]}])
def test_rejects_invalid_vehicle_list_response(
    requests_mock: requests_mock_module.Mocker,
    payload: object,
) -> None:
    requests_mock.get(f"{BASE_URL}/v1/vehicles", json=payload)
    client, _ = make_client()

    with pytest.raises(DataPortalResponseError):
        client.list_vehicles()


def test_get_battery_accepts_matching_response_vins(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    payload = battery_payload(vin=VIN.lower())
    requests_mock.get(BATTERY_URL, json=payload)
    client, _ = make_client()

    assert client.get_battery(VIN.lower()) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"batteryChargeLevelPercentage": 77}},
        battery_payload(vin="LPSVS111111111111"),
        {
            "data": {"vin": VIN, "batteryChargeLevelPercentage": 77},
            "meta": {"vin": "LPSVS111111111111", "domain": "battery"},
        },
    ],
)
def test_rejects_missing_or_mismatched_response_vin(
    requests_mock: requests_mock_module.Mocker,
    payload: dict[str, object],
) -> None:
    requests_mock.get(BATTERY_URL, json=payload)
    client, _ = make_client()

    with pytest.raises(DataPortalResponseError, match="VIN|metadata"):
        client.get_battery(VIN)


def test_extract_soc_accepts_response_without_optional_telemetry_fields() -> None:
    """Only the SoC is required for the MVP; every other Battery field is optional."""

    response = {
        "data": {"batteryChargeLevelPercentage": 77},
        "meta": {"domain": "battery"},
    }

    assert DataPortalClient.extract_soc(response) == 77.0


def test_extract_soc_ignores_unrelated_telemetry_fields() -> None:
    response = {
        "data": {
            "batteryChargeLevelPercentage": 77,
            "chargerConnectionStatus": "CHARGER_CONNECTION_STATUS_DISCONNECTED",
            "futureOptionalField": {"value": "unknown-to-this-client"},
        }
    }

    assert DataPortalClient.extract_soc(response) == 77.0


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"data": None},
        {"data": {}},
        {"data": {"batteryChargeLevelPercentage": None}},
    ],
)
def test_extract_soc_rejects_missing_required_soc(response: dict[str, object]) -> None:
    with pytest.raises(DataPortalResponseError):
        DataPortalClient.extract_soc(response)


@pytest.mark.parametrize("soc", [-1, 101, True, "77", float("nan"), float("inf")])
def test_extract_soc_rejects_invalid_values(soc: object) -> None:
    with pytest.raises(DataPortalResponseError):
        DataPortalClient.extract_soc({"data": {"batteryChargeLevelPercentage": soc}})


def test_extracts_optional_source_timestamp() -> None:
    response = battery_payload(
        timestamp={"seconds": "1788362002", "nanos": 200_583_773}
    )

    assert DataPortalClient.extract_source_timestamp(response) == datetime(
        2026,
        9,
        2,
        15,
        13,
        22,
        200_583,
        tzinfo=UTC,
    )
    assert DataPortalClient.extract_source_timestamp({"data": {}}) is None


@pytest.mark.parametrize(
    "timestamp",
    [
        "invalid",
        {},
        {"seconds": "invalid"},
        {"seconds": "1", "nanos": -1},
        {"seconds": "1", "nanos": 1_000_000_000},
        {"seconds": "1", "nanos": True},
    ],
)
def test_rejects_invalid_source_timestamp(timestamp: object) -> None:
    with pytest.raises(DataPortalResponseError, match="timestamp"):
        DataPortalClient.extract_source_timestamp({"data": {"timestamp": timestamp}})


def test_refreshes_token_exactly_once_after_unauthorized_response(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(BATTERY_URL, [
        {"status_code": 401},
        {"json": battery_payload()},
    ])
    client, provider = make_client()

    client.get_battery(VIN)

    assert provider.force_refresh_calls == [False, True]
    assert requests_mock.request_history[1].headers["Authorization"] == (
        "Bearer renewed-token"
    )


def test_stops_after_one_token_refresh(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(BATTERY_URL, status_code=401)
    client, provider = make_client()

    with pytest.raises(DataPortalAuthenticationError):
        client.get_battery(VIN)

    assert provider.force_refresh_calls == [False, True]
    assert requests_mock.call_count == 2


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, DataPortalBadRequestError),
        (403, DataPortalForbiddenError),
        (404, DataPortalNotFoundError),
        (429, DataPortalRateLimitError),
        (500, DataPortalServerError),
        (503, DataPortalServiceUnavailableError),
    ],
)
def test_maps_business_http_status_to_specific_error(
    requests_mock: requests_mock_module.Mocker,
    status_code: int,
    error_type: type[DataPortalRequestError],
) -> None:
    requests_mock.get(BATTERY_URL, status_code=status_code)
    client, _ = make_client(max_transient_retries=0)

    with pytest.raises(error_type) as exception:
        client.get_battery(VIN)

    assert exception.value.status_code == status_code


def test_retries_temporary_errors_with_exponential_jitter_and_retry_after(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(BATTERY_URL, [
        {"status_code": 503, "headers": {"Retry-After": "5"}},
        {"status_code": 429},
        {"json": battery_payload()},
    ])
    delays: list[float] = []
    client, _ = make_client(
        initial_backoff=2.0,
        sleep=delays.append,
        random_uniform=lambda minimum, maximum: maximum / 2,
    )

    assert client.get_battery(VIN) == battery_payload()
    assert delays == [5.0, 2.0]


def test_retries_transport_error_then_succeeds(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(BATTERY_URL, [
        {"exc": requests.Timeout("temporary timeout")},
        {"json": battery_payload()},
    ])
    delays: list[float] = []
    client, _ = make_client(
        sleep=delays.append,
        random_uniform=lambda minimum, maximum: maximum,
    )

    assert client.get_battery(VIN) == battery_payload()
    assert delays == [1.0]


def test_honors_http_date_retry_after(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(BATTERY_URL, [
        {
            "status_code": 503,
            "headers": {"Retry-After": "Wed, 02 Sep 2026 15:13:27 GMT"},
        },
        {"json": battery_payload()},
    ])
    delays: list[float] = []
    client, _ = make_client(
        sleep=delays.append,
        random_uniform=lambda minimum, maximum: 0.0,
        utcnow=lambda: datetime(2026, 9, 2, 15, 13, 22, tzinfo=UTC),
    )

    client.get_battery(VIN)

    assert delays == [5.0]
