"""Polestar Data Portal API boundary."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import requests


DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0
BATTERY_SCOPE = "pdp-telemetry/battery"


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
