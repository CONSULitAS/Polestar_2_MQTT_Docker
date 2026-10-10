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


def catalog_for_tests():
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog

    return build_endpoint_catalog({"paths": {
        f"/v1/vehicles/{{vin}}/telemetry/{name}": {
            "get": {"x-required-scopes": ["test/read"]},
        } for name in ("a", "b", "new-field")
    }})


# Jeder Katalogendpunkt wird sequenziell abgerufen und seiner Antwort zugeordnet.
def test_catalog_requests_all_endpoints_in_order(requests_mock):
    catalog = catalog_for_tests()
    for endpoint in catalog:
        requests_mock.get(BASE_URL + endpoint.request_path(VIN), json={"data": {"new": 7}})
    client, _ = make_client()
    results, failures = client.get_catalog(catalog, VIN)
    assert failures == {}
    assert list(results) == [endpoint.path_template for endpoint in catalog]
    assert [request.url for request in requests_mock.request_history] == [
        BASE_URL + endpoint.request_path(VIN) for endpoint in catalog
    ]
    assert all(response == {"data": {"new": 7}} for response in results.values())


# Ein fehlerhafter Endpunkt lässt erfolgreiche Antworten anderer Endpunkte bestehen.
def test_catalog_preserves_successes_despite_endpoint_error(requests_mock, caplog):
    catalog = catalog_for_tests()
    for endpoint in catalog:
        requests_mock.get(BASE_URL + endpoint.request_path(VIN), json={"data": {}})
    requests_mock.get(BASE_URL + catalog[0].request_path(VIN), status_code=404, json={})
    client, _ = make_client()
    results, failures = client.get_catalog(catalog, VIN)
    assert list(results) == [endpoint.path_template for endpoint in catalog[1:]]
    assert failures == {catalog[0].path_template: "DataPortalNotFoundError"}
    assert requests_mock.call_count == len(catalog)
    assert "404 / HTTP_ERROR: No valid API error message" in caplog.text
    assert VIN not in caplog.text
    assert "cached-token" not in caplog.text


@pytest.mark.parametrize("status", [404, 503])
# Die passende Fehlermeldung sperrt nur den betroffenen Endpunkt bis zum neuen Client.
def test_matching_message_excludes_only_current_endpoint_until_new_client(
    requests_mock, caplog, status,
):
    catalog = catalog_for_tests()
    unavailable = BASE_URL + catalog[0].request_path(VIN)
    for endpoint in catalog:
        requests_mock.get(BASE_URL + endpoint.request_path(VIN), json={"data": {}})
    requests_mock.get(unavailable, status_code=status, json={"error": {
        "code": "DATA_NOT_AVAILABLE",
        "message": "No a data is available for this vehicle.",
    }})
    client, _ = make_client(sleep=lambda _: pytest.fail("Excluded endpoint must not retry"))
    _, failures = client.get_catalog(catalog, VIN)
    assert catalog[0].path_template in failures
    _, failures = client.get_catalog(catalog, VIN)
    assert failures == {catalog[0].path_template: "DataPortalEndpointExcludedError"}
    assert [r.url for r in requests_mock.request_history].count(unavailable) == 1
    assert requests_mock.call_count == 5
    assert caplog.messages == [
        f"{status} / DATA_NOT_AVAILABLE: No a data is available for this vehicle.",
    ]
    replacement, _ = make_client(sleep=lambda _: None)
    replacement.get_catalog(catalog, VIN)
    assert [r.url for r in requests_mock.request_history].count(unavailable) == 2


@pytest.mark.parametrize("body", [
    {"error": {"code": "DATA_NOT_AVAILABLE", "message": "Try again later"}},
    {"error": {"code": "NOT_FOUND", "message": "Unknown endpoint"}},
    {"error": {"code": "DATA_NOT_AVAILABLE", "message": None}},
    [],
])
# Fehlermeldungen ohne das vereinbarte Muster lösen keinen Laufzeitausschluss aus.
def test_nonmatching_errors_do_not_exclude_endpoint(requests_mock, body):
    endpoint = catalog_for_tests()[0]
    requests_mock.get(BASE_URL + endpoint.request_path(VIN), status_code=404, json=body)
    client, _ = make_client()
    client.get_catalog((endpoint,), VIN)
    client.get_catalog((endpoint,), VIN)
    assert requests_mock.call_count == 2


# Jeder Retry-Fehler zeigt Status, Code und Meldung ohne VIN oder Zugangsdaten.
def test_each_retry_error_is_logged_and_sensitive_values_are_redacted(requests_mock, caplog):
    endpoint = catalog_for_tests()[0]
    requests_mock.get(BASE_URL + endpoint.request_path(VIN), [
        {"status_code": 503, "json": {"error": {
            "code": "UNAVAILABLE", "message": f"Retry {VIN} cached-token account-id\nplease",
        }}},
        {"status_code": 401, "json": {"error": {
            "code": "EXPIRED", "message": "New token required",
        }}},
        {"json": {"data": {}}},
    ])
    client, _ = make_client(sleep=lambda _: None)
    client.get_endpoint(endpoint, VIN)
    assert caplog.messages == [
        "503 / UNAVAILABLE: Retry [REDACTED] [REDACTED] [REDACTED] please",
        "401 / EXPIRED: New token required",
    ]


# Fehler ohne JSON-Body erhalten eine sichere Ersatzmeldung statt des Rohinhalts.
def test_non_json_error_body_has_safe_fallback(requests_mock, caplog):
    endpoint = catalog_for_tests()[0]
    requests_mock.get(
        BASE_URL + endpoint.request_path(VIN), status_code=404, text="private diagnostic HTML",
    )
    client, _ = make_client()
    client.get_catalog((endpoint,), VIN)
    assert caplog.messages == ["404 / HTTP_ERROR: No valid API error message"]


@pytest.mark.parametrize("payload", [None, [], "not an object", 3])
# Generische Fahrzeugantworten müssen JSON-Objekte sein.
def test_generic_endpoint_rejects_non_object_responses(requests_mock, payload):
    endpoint = catalog_for_tests()[0]
    requests_mock.get(BASE_URL + endpoint.request_path(VIN), json=payload)
    client, _ = make_client()
    with pytest.raises(DataPortalResponseError):
        client.get_endpoint(endpoint, VIN)


# Temporäre Fehler und 401 verwenden auch beim generischen Abruf die bestehende Retry-Logik.
def test_generic_endpoint_reuses_401_and_transient_retry(requests_mock):
    endpoint = catalog_for_tests()[0]
    requests_mock.get(BASE_URL + endpoint.request_path(VIN), [
        {"status_code": 503}, {"status_code": 401}, {"json": {"data": {}}},
    ])
    delays = []
    client, provider = make_client(sleep=delays.append)
    assert client.get_endpoint(endpoint, VIN) == {"data": {}}
    assert len(delays) == 1
    assert provider.force_refresh_calls == [False, False, True]


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


# Fahrzeugabrufe erhalten Bearer-Token, Account-Zuordnung und JSON-Accept-Header.
def test_builds_required_authorization_headers() -> None:
    client, _ = make_client()

    assert client.authorization_headers() == {
        "Accept": "application/json",
        "Authorization": "Bearer cached-token",
        "x-client-id": "account-id",
    }


# Die konfigurierte VIN wird unabhängig von Großschreibung in der Fahrzeugliste erkannt.
def test_lists_vehicles_and_authorizes_vin_case_insensitively(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(f"{BASE_URL}/v1/vehicles", json={"data": [VIN.lower()]})
    client, _ = make_client()

    client.ensure_vehicle_authorized(VIN)

    assert requests_mock.last_request.headers["Authorization"] == "Bearer cached-token"


# Eine nicht autorisierte VIN wird vor fachlichen Fahrzeugabrufen zurückgewiesen.
def test_rejects_vin_missing_from_authorized_vehicles(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.get(f"{BASE_URL}/v1/vehicles", json={"data": []})
    client, _ = make_client()

    with pytest.raises(VehicleNotAuthorizedError):
        client.ensure_vehicle_authorized(VIN)


@pytest.mark.parametrize("payload", [None, [], {}, {"data": None}, {"data": [""]}])
# Eine fehlerhafte Fahrzeugliste darf keine VIN-Autorisierung begründen.
def test_rejects_invalid_vehicle_list_response(
    requests_mock: requests_mock_module.Mocker,
    payload: object,
) -> None:
    requests_mock.get(f"{BASE_URL}/v1/vehicles", json=payload)
    client, _ = make_client()

    with pytest.raises(DataPortalResponseError):
        client.list_vehicles()


# Battery-Daten werden akzeptiert, wenn die Antwort-VINs zum angefragten Fahrzeug passen.
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
# Fehlende oder abweichende Antwort-VINs verhindern die Übernahme der Battery-Daten.
def test_rejects_missing_or_mismatched_response_vin(
    requests_mock: requests_mock_module.Mocker,
    payload: dict[str, object],
) -> None:
    requests_mock.get(BATTERY_URL, json=payload)
    client, _ = make_client()

    with pytest.raises(DataPortalResponseError, match="VIN|metadata"):
        client.get_battery(VIN)


# Für die SoC-Ableitung genügt ein gültiger Ladezustand ohne optionale Battery-Felder.
def test_extract_soc_accepts_response_without_optional_telemetry_fields() -> None:
    """Only the SoC is required for the MVP; every other Battery field is optional."""

    response = {
        "data": {"batteryChargeLevelPercentage": 77},
        "meta": {"domain": "battery"},
    }

    assert DataPortalClient.extract_soc(response) == 77.0


# Zusätzliche Telemetriefelder verändern die Ableitung des vorhandenen SoC nicht.
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
# Fehlender oder auf null gesetzter SoC gilt nicht als gültiger Messwert.
def test_extract_soc_rejects_missing_required_soc(response: dict[str, object]) -> None:
    with pytest.raises(DataPortalResponseError):
        DataPortalClient.extract_soc(response)


@pytest.mark.parametrize("soc", [-1, 101, True, "77", float("nan"), float("inf")])
# Nur endliche numerische SoC-Werte von 0 bis 100 werden akzeptiert.
def test_extract_soc_rejects_invalid_values(soc: object) -> None:
    with pytest.raises(DataPortalResponseError):
        DataPortalClient.extract_soc({"data": {"batteryChargeLevelPercentage": soc}})


# Der optionale API-Zeitstempel wird aus Sekunden und Nanosekunden nach UTC umgerechnet.
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
# Fehlerhafte Sekunden oder Nanosekunden werden nicht als Quellzeitstempel übernommen.
def test_rejects_invalid_source_timestamp(timestamp: object) -> None:
    with pytest.raises(DataPortalResponseError, match="timestamp"):
        DataPortalClient.extract_source_timestamp({"data": {"timestamp": timestamp}})


# Nach 401 wird einmal ein neues Token geholt und der Fahrzeugabruf wiederholt.
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


# Ein erneutes 401 beendet den Abruf ohne weitere Token-Erneuerung.
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
# HTTP-Fehler werden in die jeweils passende fachliche Exception übersetzt.
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


# Temporäre Fehler nutzen begrenztes Backoff mit Jitter und beachten Retry-After.
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


# Ein vorübergehender Transportfehler wird wiederholt und kann erfolgreich enden.
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


# Ein Retry-After-Datum bestimmt die nötige Wartezeit vor dem nächsten Abruf.
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
