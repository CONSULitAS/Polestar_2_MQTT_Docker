from graphql_queries import (
    build_cartelematicsv2_payload,
    build_getconsumercarsv2_payload,
)


def test_build_getconsumercarsv2_payload_uses_expected_operation_and_query():
    payload = build_getconsumercarsv2_payload()

    assert payload["operationName"] == "GetConsumerCarsV2"
    assert payload["variables"] == "{}"
    assert "query GetConsumerCarsV2" in payload["query"]
    assert "getConsumerCarsV2" in payload["query"]


def test_build_cartelematicsv2_payload_contains_requested_vin():
    payload = build_cartelematicsv2_payload("VIN123")

    assert payload["operationName"] == "CarTelematicsV2"
    assert payload["variables"] == {"vins": "VIN123"}
    assert "query CarTelematicsV2" in payload["query"]
    assert "carTelematicsV2" in payload["query"]
