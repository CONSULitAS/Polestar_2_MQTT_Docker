# Unit tests

This directory contains deterministic tests for the `polestar_mqtt` package.
Tests in this directory must not access the network or require real Polestar,
MQTT, or openWB credentials.

Sanitized API response fixtures are stored in `tests/fixtures/data_portal`.
Containerized live checks belong to the explicitly invoked M4A and M8 quality
gates, not to the unit-test suite.

