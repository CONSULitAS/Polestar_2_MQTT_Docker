"""Redaction checks for the temporary response diagnostic."""

from polestar_mqtt.debug_responses import redact_response


# Die Diagnose zeigt Nutzdaten und Fehler, maskiert aber VIN und Zugangsdaten.
def test_diagnostic_keeps_data_and_errors_but_redacts_identifiers():
    response = {
        "data": {"soc": 50, "coordinates": [1.2, 3.4], "vin": "fixture-vin"},
        "accessToken": "fixture-token", "clientSecret": "fixture-secret",
        "message": "No data for fixture-vin using fixture-token",
        "code": "DATA_NOT_AVAILABLE",
    }
    result = redact_response(response, ("fixture-vin", "fixture-token", "fixture-secret"))
    assert result["data"] == {"soc": 50, "coordinates": [1.2, 3.4], "vin": "[REDACTED]"}
    assert result["accessToken"] == result["clientSecret"] == "[REDACTED]"
    assert result["message"] == "No data for [REDACTED] using [REDACTED]"
    assert result["code"] == "DATA_NOT_AVAILABLE"
