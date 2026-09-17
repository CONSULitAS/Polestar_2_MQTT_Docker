"""Local quality gate for one live State of Charge read."""

from __future__ import annotations

import json

from polestar_mqtt.config import ConfigurationError, DataPortalConfig
from polestar_mqtt.polestar_api import (
    DataPortalClient,
    DataPortalHttpClient,
    DataPortalRequestError,
    DataPortalResponseError,
    TokenProvider,
    TokenProviderError,
)


def main() -> int:
    """Authorize the configured VIN and print only its validated SoC."""

    try:
        config = DataPortalConfig.from_environment()
    except ConfigurationError as error:
        print(f"SoC check configuration error: {error}")
        return 2

    try:
        with DataPortalHttpClient(config.api_base_url) as http_client:
            token_provider = TokenProvider(
                http_client,
                config.client_id,
                config.client_secret,
            )
            client = DataPortalClient(
                http_client,
                token_provider,
                config.account_id,
            )
            client.ensure_vehicle_authorized(config.vin)
            soc = client.extract_soc(client.get_battery(config.vin))
    except (TokenProviderError, DataPortalRequestError, DataPortalResponseError) as error:
        print(f"SoC check failed: {config.redact(str(error))}")
        return 1

    print(json.dumps({"live_data": "successful", "soc_percent": soc}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
