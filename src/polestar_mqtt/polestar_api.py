"""Polestar Data Portal API boundary."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Callable
from urllib.parse import quote

import requests

from polestar_mqtt.config import VIN_PATTERN, redact_sensitive_text


DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0
BATTERY_SCOPE = "pdp-telemetry/battery"
TOKEN_EXPIRY_MARGIN_SECONDS = 60.0
TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 503})
DEFAULT_MAX_TRANSIENT_RETRIES = 3
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0


class TokenProviderError(RuntimeError):
    """Base class for safe token-provider failures."""


class TokenRequestError(TokenProviderError):
    """Raised when the identity service rejects or cannot process a request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TokenResponseError(TokenProviderError):
    """Raised when a successful response does not match the token contract."""


class DataPortalRequestError(RuntimeError):
    """Raised when a Data Portal business request is rejected."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DataPortalAuthenticationError(DataPortalRequestError):
    """Raised when a request remains unauthorized after token renewal."""


class DataPortalBadRequestError(DataPortalRequestError):
    """Raised when the API rejects malformed request parameters."""


class DataPortalForbiddenError(DataPortalRequestError):
    """Raised when the credential lacks scope or vehicle permission."""


class DataPortalNotFoundError(DataPortalRequestError):
    """Raised when the requested vehicle data is unavailable."""


class DataPortalRateLimitError(DataPortalRequestError):
    """Raised when rate limiting persists after bounded retries."""


class DataPortalServerError(DataPortalRequestError):
    """Raised when an internal API error persists after bounded retries."""


class DataPortalServiceUnavailableError(DataPortalRequestError):
    """Raised when the vehicle-state provider remains unavailable."""


class DataPortalResponseError(RuntimeError):
    """Raised when a Data Portal response violates its documented contract."""


class VehicleNotAuthorizedError(DataPortalRequestError):
    """Raised when the configured VIN is absent from the account binding."""


@dataclass(frozen=True)
class AccessToken:
    """Validated in-memory representation of one OAuth access token."""

    value: str = field(repr=False)
    token_type: str
    expires_in: float
    expires_at_monotonic: float = field(repr=False)


class DataPortalHttpClient:
    """Small reusable HTTP transport for the Data Portal API.

    Authentication, retries, and response interpretation intentionally remain
    outside this transport and are added by later migration tasks.
    """

    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (
            DEFAULT_CONNECT_TIMEOUT_SECONDS,
            DEFAULT_READ_TIMEOUT_SECONDS,
        ),
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if timeout[0] <= 0 or timeout[1] <= 0:
            raise ValueError("HTTP timeouts must be greater than zero")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self.session.headers.setdefault("Accept", "application/json")

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Send one request using the shared session and default timeouts."""

        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        kwargs.setdefault("timeout", self.timeout)
        return self.session.request(method, f"{self.base_url}{path}", **kwargs)

    def request_token(
        self,
        client_id: str,
        client_secret: str,
    ) -> requests.Response:
        """Request an access token with the minimum Battery scope."""

        return self.request(
            "POST",
            "/token",
            json={
                "clientId": client_id,
                "clientSecret": client_secret,
                "scope": BATTERY_SCOPE,
            },
        )

    def close(self) -> None:
        """Close a session created by this client."""

        if self._owns_session:
            self.session.close()

    def __enter__(self) -> DataPortalHttpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class TokenProvider:
    """Obtain and cache OAuth tokens using the client-credentials grant."""

    def __init__(
        self,
        http_client: DataPortalHttpClient,
        client_id: str,
        client_secret: str,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http_client = http_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._monotonic = monotonic
        self._token: AccessToken | None = None

    def get_token(self, *, force_refresh: bool = False) -> AccessToken:
        """Return a valid cached token or request a new one before expiry."""

        now = self._monotonic()
        if (
            not force_refresh
            and self._token is not None
            and now
            < self._token.expires_at_monotonic - TOKEN_EXPIRY_MARGIN_SECONDS
        ):
            return self._token

        self._token = self._request_new_token(now)
        return self._token

    def _request_new_token(self, requested_at: float) -> AccessToken:
        try:
            response = self._http_client.request_token(
                self._client_id,
                self._client_secret,
            )
        except requests.RequestException as error:
            safe_message = redact_sensitive_text(str(error), self._client_secret)
            raise TokenRequestError(
                f"Token request failed: {safe_message or type(error).__name__}"
            ) from error

        payload = self._read_json_object(response)
        if response.status_code != 200:
            error_name = payload.get("error", "token_request_failed")
            description = payload.get("error_description", "request rejected")
            safe_detail = redact_sensitive_text(
                f"{error_name}: {description}",
                self._client_secret,
            )
            raise TokenRequestError(
                f"Token endpoint returned HTTP {response.status_code}: {safe_detail}",
                status_code=response.status_code,
            )

        access_token = payload.get("accessToken")
        token_type = payload.get("tokenType")
        expires_in = payload.get("expiresIn")
        if not isinstance(access_token, str) or not access_token:
            raise TokenResponseError("Token response contains no valid accessToken")
        if not isinstance(token_type, str) or not token_type:
            raise TokenResponseError("Token response contains no valid tokenType")
        if (
            isinstance(expires_in, bool)
            or not isinstance(expires_in, (int, float))
            or expires_in <= 0
        ):
            raise TokenResponseError("Token response contains no valid expiresIn")

        return AccessToken(
            value=access_token,
            token_type=token_type,
            expires_in=float(expires_in),
            expires_at_monotonic=requested_at + float(expires_in),
        )

    @staticmethod
    def _read_json_object(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise TokenResponseError("Token endpoint returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise TokenResponseError("Token endpoint returned a non-object JSON response")
        return payload


class DataPortalClient:
    """Authorized client for official Data Portal business endpoints."""

    def __init__(
        self,
        http_client: DataPortalHttpClient,
        token_provider: TokenProvider,
        account_id: str,
        *,
        max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not account_id.strip():
            raise ValueError("account_id must not be empty")
        if max_transient_retries < 0:
            raise ValueError("max_transient_retries must not be negative")
        if initial_backoff <= 0 or max_backoff <= 0:
            raise ValueError("backoff values must be greater than zero")
        self._http_client = http_client
        self._token_provider = token_provider
        self._account_id = account_id.strip()
        self._max_transient_retries = max_transient_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._sleep = sleep
        self._random_uniform = random_uniform
        self._utcnow = utcnow

    def authorization_headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        """Build the required headers without persisting them on the session."""

        token = self._token_provider.get_token(force_refresh=force_refresh)
        return {
            "Accept": "application/json",
            "Authorization": f"{token.token_type} {token.value}",
            "x-client-id": self._account_id,
        }

    def list_vehicles(self) -> list[str]:
        """Return the VINs authorized for the configured account binding."""

        response = self._authorized_get("/v1/vehicles", "Vehicle list")

        try:
            payload = response.json()
        except ValueError as error:
            raise DataPortalResponseError(
                "Vehicle list endpoint returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise DataPortalResponseError(
                "Vehicle list endpoint returned a non-object JSON response"
            )

        vehicles = payload.get("data")
        if not isinstance(vehicles, list) or any(
            not isinstance(vin, str) or not vin for vin in vehicles
        ):
            raise DataPortalResponseError(
                "Vehicle list response contains no valid data array"
            )
        return vehicles

    def ensure_vehicle_authorized(self, vin: str) -> None:
        """Ensure the configured VIN belongs to the authenticated account."""

        normalized_vin = vin.strip().upper()
        if not normalized_vin:
            raise ValueError("vin must not be empty")
        authorized_vins = {value.upper() for value in self.list_vehicles()}
        if normalized_vin not in authorized_vins:
            raise VehicleNotAuthorizedError(
                "Configured VIN is not authorized for the Data Portal account"
            )

    def get_battery(self, vin: str) -> dict[str, Any]:
        """Fetch the official Battery telemetry response for one vehicle."""

        normalized_vin = vin.strip().upper()
        if not VIN_PATTERN.fullmatch(normalized_vin):
            raise ValueError("vin must be a valid 17-character VIN")
        encoded_vin = quote(normalized_vin, safe="")
        response = self._authorized_get(
            f"/v1/vehicles/{encoded_vin}/telemetry/battery",
            "Battery",
        )

        try:
            payload = response.json()
        except ValueError as error:
            raise DataPortalResponseError(
                "Battery endpoint returned invalid JSON"
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise DataPortalResponseError(
                "Battery endpoint returned no valid data object"
            )
        self._validate_response_vin(payload, normalized_vin)
        return payload

    def _authorized_get(self, path: str, endpoint_name: str) -> requests.Response:
        transient_retries = 0
        token_refreshed = False

        while True:
            try:
                response = self._http_client.request(
                    "GET",
                    path,
                    headers=self.authorization_headers(
                        force_refresh=token_refreshed,
                    ),
                )
            except requests.RequestException as error:
                if transient_retries >= self._max_transient_retries:
                    raise DataPortalRequestError(
                        f"{endpoint_name} request failed after retries: "
                        f"{type(error).__name__}"
                    ) from error
                self._sleep(self._backoff_seconds(transient_retries, None))
                transient_retries += 1
                token_refreshed = False
                continue

            if response.status_code == 200:
                return response
            if response.status_code == 401 and not token_refreshed:
                token_refreshed = True
                continue
            if (
                response.status_code in TRANSIENT_HTTP_STATUS_CODES
                and transient_retries < self._max_transient_retries
            ):
                self._sleep(self._backoff_seconds(transient_retries, response))
                transient_retries += 1
                token_refreshed = False
                continue
            self._raise_for_status(response.status_code, endpoint_name)

    def _backoff_seconds(
        self,
        retry_number: int,
        response: requests.Response | None,
    ) -> float:
        maximum = min(
            self._initial_backoff * (2**retry_number),
            self._max_backoff,
        )
        delay = self._random_uniform(0.0, maximum)
        if response is not None:
            retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
            if retry_after is not None:
                delay = max(delay, retry_after)
        return delay

    def _parse_retry_after(self, value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(
                0.0,
                (retry_at.astimezone(UTC) - self._utcnow().astimezone(UTC)).total_seconds(),
            )

    @staticmethod
    def _raise_for_status(status_code: int, endpoint_name: str) -> None:
        error_types: dict[int, type[DataPortalRequestError]] = {
            400: DataPortalBadRequestError,
            401: DataPortalAuthenticationError,
            403: DataPortalForbiddenError,
            404: DataPortalNotFoundError,
            429: DataPortalRateLimitError,
            500: DataPortalServerError,
            503: DataPortalServiceUnavailableError,
        }
        error_type = error_types.get(status_code, DataPortalRequestError)
        raise error_type(
            f"{endpoint_name} endpoint returned HTTP {status_code}",
            status_code=status_code,
        )

    @staticmethod
    def _validate_response_vin(
        battery_response: dict[str, Any],
        expected_vin: str,
    ) -> None:
        meta = battery_response.get("meta")
        if not isinstance(meta, dict):
            raise DataPortalResponseError(
                "Battery response contains no valid metadata object"
            )

        response_vins = (meta.get("vin"), battery_response["data"].get("vin"))
        present_vins = [vin for vin in response_vins if vin is not None]
        if not present_vins or any(not isinstance(vin, str) for vin in present_vins):
            raise DataPortalResponseError("Battery response contains no valid VIN")
        if any(vin.strip().upper() != expected_vin for vin in present_vins):
            raise DataPortalResponseError(
                "Battery response VIN does not match the requested vehicle"
            )

    @staticmethod
    def extract_soc(battery_response: dict[str, Any]) -> float:
        """Extract a finite State of Charge percentage in the range 0..100."""

        battery_data = battery_response.get("data")
        if not isinstance(battery_data, dict):
            raise DataPortalResponseError(
                "Battery response contains no valid data object"
            )
        soc = battery_data.get("batteryChargeLevelPercentage")
        if isinstance(soc, bool) or not isinstance(soc, (int, float)):
            raise DataPortalResponseError(
                "Battery response contains no numeric charge level"
            )
        normalized_soc = float(soc)
        if not math.isfinite(normalized_soc) or not 0 <= normalized_soc <= 100:
            raise DataPortalResponseError(
                "Battery charge level must be between 0 and 100"
            )
        return normalized_soc

    @staticmethod
    def extract_source_timestamp(
        battery_response: dict[str, Any],
    ) -> datetime | None:
        """Return an optional protobuf telemetry timestamp as UTC datetime."""

        battery_data = battery_response.get("data")
        if not isinstance(battery_data, dict):
            raise DataPortalResponseError(
                "Battery response contains no valid data object"
            )
        timestamp = battery_data.get("timestamp")
        if timestamp is None:
            return None
        if not isinstance(timestamp, dict):
            raise DataPortalResponseError("Battery timestamp must be an object")

        seconds = timestamp.get("seconds")
        nanos = timestamp.get("nanos", 0)
        try:
            parsed_seconds = int(seconds)
        except (TypeError, ValueError) as error:
            raise DataPortalResponseError(
                "Battery timestamp contains invalid seconds"
            ) from error
        if isinstance(nanos, bool) or not isinstance(nanos, int) or not 0 <= nanos < 1_000_000_000:
            raise DataPortalResponseError(
                "Battery timestamp contains invalid nanoseconds"
            )
        try:
            return datetime.fromtimestamp(parsed_seconds, UTC) + timedelta(
                microseconds=nanos // 1_000
            )
        except (OverflowError, OSError, ValueError) as error:
            raise DataPortalResponseError(
                "Battery timestamp is outside the supported range"
            ) from error
