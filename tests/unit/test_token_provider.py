"""Unit tests for the official Data Portal token flow."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests
import requests_mock as requests_mock_module

from polestar_mqtt.polestar_api import (
    BATTERY_SCOPE,
    DataPortalHttpClient,
    TokenProvider,
    TokenRequestError,
    TokenResponseError,
)


BASE_URL = "https://example.invalid/m2m"
TOKEN_URL = f"{BASE_URL}/token"
FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "data_portal"


class FakeClock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def make_provider(clock: FakeClock) -> TokenProvider:
    return TokenProvider(
        DataPortalHttpClient(BASE_URL),
        "client-id",
        "client-secret",
        monotonic=clock,
    )


# Client-Credentials liefern ein validiertes Bearer-Token mit berechneter Ablaufzeit.
def test_requests_and_validates_json_token(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.post(TOKEN_URL, json={
        "accessToken": "access-token-value",
        "expiresIn": 3600,
        "tokenType": "Bearer",
    })
    clock = FakeClock()

    token = make_provider(clock).get_token()

    assert token.value == "access-token-value"
    assert token.token_type == "Bearer"
    assert token.expires_in == 3600.0
    assert token.expires_at_monotonic == 4600.0
    assert requests_mock.last_request.json() == {
        "clientId": "client-id",
        "clientSecret": "client-secret",
        "scope": BATTERY_SCOPE,
    }
    assert requests_mock.last_request.headers["Content-Type"].startswith(
        "application/json"
    )


# Ein Token wird bis zur Sicherheitsmarge wiederverwendet und dann ersetzt.
def test_reuses_token_until_expiry_margin(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.post(TOKEN_URL, [
        {"json": {"accessToken": "first", "expiresIn": 3600, "tokenType": "Bearer"}},
        {"json": {"accessToken": "second", "expiresIn": 3600, "tokenType": "Bearer"}},
    ])
    clock = FakeClock()
    provider = make_provider(clock)

    first = provider.get_token()
    clock.value = first.expires_at_monotonic - 61
    assert provider.get_token() is first
    assert requests_mock.call_count == 1

    clock.value = first.expires_at_monotonic - 60
    second = provider.get_token()
    assert second.value == "second"
    assert requests_mock.call_count == 2


# Eine erzwungene Erneuerung ersetzt auch ein noch gültiges Token.
def test_force_refresh_requests_new_token(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.post(TOKEN_URL, [
        {"json": {"accessToken": "first", "expiresIn": 3600, "tokenType": "Bearer"}},
        {"json": {"accessToken": "second", "expiresIn": 3600, "tokenType": "Bearer"}},
    ])
    provider = make_provider(FakeClock())

    assert provider.get_token().value == "first"
    assert provider.get_token(force_refresh=True).value == "second"
    assert requests_mock.call_count == 2


@pytest.mark.parametrize("status_code", [400, 401, 500, 502, 503])
# Token-HTTP-Fehler behalten ihren Status, geben aber das Client Secret nicht preis.
def test_maps_http_errors_to_redacted_exception(
    requests_mock: requests_mock_module.Mocker,
    status_code: int,
) -> None:
    requests_mock.post(TOKEN_URL, status_code=status_code, json={
        "error": "invalid_client",
        "error_description": "rejected client-secret",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    with pytest.raises(TokenRequestError) as exception:
        make_provider(FakeClock()).get_token()

    assert exception.value.status_code == status_code
    assert "client-secret" not in str(exception.value)
    assert "[REDACTED]" in str(exception.value)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"expiresIn": 3600, "tokenType": "Bearer"},
        {"accessToken": "token", "tokenType": "Bearer"},
        {"accessToken": "token", "expiresIn": 0, "tokenType": "Bearer"},
        {"accessToken": "token", "expiresIn": True, "tokenType": "Bearer"},
        {"accessToken": "token", "expiresIn": 3600},
        ["not", "an", "object"],
    ],
)
# Eine erfolgreiche HTTP-Antwort ohne gültige Token-Daten wird abgelehnt.
def test_rejects_invalid_success_response(
    requests_mock: requests_mock_module.Mocker,
    response: object,
) -> None:
    requests_mock.post(TOKEN_URL, json=response)

    with pytest.raises(TokenResponseError):
        make_provider(FakeClock()).get_token()


# Ungültiges JSON der Token-Antwort wird als Antwortfehler gemeldet.
def test_rejects_invalid_json(requests_mock: requests_mock_module.Mocker) -> None:
    requests_mock.post(TOKEN_URL, text="not-json")

    with pytest.raises(TokenResponseError, match="invalid JSON"):
        make_provider(FakeClock()).get_token()


# Ein Timeout beim Tokenabruf darf das Client Secret nicht offenlegen.
def test_maps_timeout_without_leaking_secret(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.post(
        TOKEN_URL,
        exc=requests.Timeout("timeout while sending client-secret"),
    )

    with pytest.raises(TokenRequestError) as exception:
        make_provider(FakeClock()).get_token()

    assert "client-secret" not in str(exception.value)
    assert "[REDACTED]" in str(exception.value)


# Die Darstellung des Token-Objekts enthält keinen Access Token.
def test_token_repr_does_not_contain_access_token(
    requests_mock: requests_mock_module.Mocker,
) -> None:
    requests_mock.post(TOKEN_URL, json={
        "accessToken": "access-token-value",
        "expiresIn": 3600,
        "tokenType": "Bearer",
    })

    token = make_provider(FakeClock()).get_token()

    assert "access-token-value" not in repr(token)


# Cache, Ablauf und erzwungene Erneuerung verwenden denselben Scope-Satz.
def test_scope_snapshot_survives_cache_expiry_and_forced_renewal(requests_mock):
    requests_mock.post(TOKEN_URL, json={
        "accessToken": "fixture-token", "expiresIn": 3600, "tokenType": "Bearer",
    })
    clock = FakeClock()
    scope = "pdp-charging/targetSoc pdp-telemetry/battery"
    provider = TokenProvider(
        DataPortalHttpClient(BASE_URL), "client-id", "client-secret",
        scope=scope, monotonic=clock,
    )
    first = provider.get_token()
    assert provider.get_token() is first
    assert requests_mock.call_count == 1
    clock.value = first.expires_at_monotonic
    provider.get_token()
    provider.get_token(force_refresh=True)
    assert requests_mock.call_count == 3
    assert all(request.json()["scope"] == scope for request in requests_mock.request_history)
