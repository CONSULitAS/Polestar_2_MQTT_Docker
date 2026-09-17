"""Container-friendly authentication-only quality gate."""

from __future__ import annotations

import json

from polestar_mqtt.config import ConfigurationError, DataPortalConfig
from polestar_mqtt.polestar_api import (
    DataPortalHttpClient,
    TokenProvider,
    TokenProviderError,
)


def main() -> int:
    """Request one token and print only non-sensitive result metadata."""

    try:
        config = DataPortalConfig.from_environment()
    except ConfigurationError as error:
        print(f"Authentication check configuration error: {error}")
        return 2

    try:
        with DataPortalHttpClient(config.api_base_url) as http_client:
            token = TokenProvider(
                http_client,
                config.client_id,
                config.client_secret,
            ).get_token()
    except TokenProviderError as error:
        print(f"Authentication check failed: {config.redact(str(error))}")
        return 1

    print(
        json.dumps(
            {
                "authentication": "successful",
                "token_type": token.token_type,
                "expires_in": token.expires_in,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
