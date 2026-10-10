"""Temporary, explicitly invoked GET-response diagnostic; never publishes MQTT."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from polestar_mqtt.config import DataPortalConfig, redact_sensitive_text
from polestar_mqtt.openapi_catalog import (
    aggregate_scopes, build_endpoint_catalog, load_openapi_document,
)
from polestar_mqtt.polestar_api import DataPortalClient, DataPortalHttpClient, TokenProvider


def redact_response(value, sensitive_values):
    """Keep telemetry while masking identifiers and authentication material."""

    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower().replace("_", "") in {
                "vin", "accesstoken", "refreshtoken", "token", "clientsecret",
                "secret", "password", "authorization",
            } else redact_response(child, sensitive_values)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_response(child, sensitive_values) for child in value]
    if isinstance(value, str):
        return redact_sensitive_text(value, *sensitive_values)
    return value


def main() -> int:
    records = []
    try:
        config = DataPortalConfig.from_environment()
        catalog = build_endpoint_catalog(load_openapi_document(config.openapi_file))

        def capture(response, *args, **kwargs):
            if response.request.method != "GET":
                return
            token = response.request.headers.get("Authorization", "").removeprefix("Bearer ")
            sensitive = (
                config.vin, config.vin.lower(), config.client_id, config.client_secret,
                config.account_id, config.mqtt_password, token,
            )
            try:
                body = response.json()
            except ValueError:
                body = response.text
            records.append({
                "path": redact_sensitive_text(
                    response.request.path_url, config.vin, config.vin.lower(),
                ),
                "status": response.status_code,
                "body": redact_response(body, sensitive),
            })

        with DataPortalHttpClient(config.api_base_url) as http:
            http.session.hooks["response"].append(capture)
            provider = TokenProvider(
                http, config.client_id, config.client_secret, scope=aggregate_scopes(catalog),
            )
            api = DataPortalClient(http, provider, config.account_id)
            api.ensure_vehicle_authorized(config.vin)
            _, failures = api.get_catalog(catalog, config.vin)
        report = json.dumps(
            {"responses": records, "failures": failures}, indent=2, ensure_ascii=False,
        )
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="polestar-debug-", suffix=".json", delete=False,
        ) as output:
            output.write(report + "\n")
            report_path = Path(output.name)
        print(report)
        print(f"Debug report: {report_path}")
        return 0
    except Exception as error:
        print(f"Data Portal debug failed ({type(error).__name__})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
