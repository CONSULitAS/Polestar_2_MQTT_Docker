# MQTT broker integration tests

These checks start a temporary Mosquitto process bound only to `127.0.0.1` on an
unused port. Each test has its own broker, configuration and topic inventory.
Polestar HTTP responses are mocked with synthetic data. Neither `.env` nor
`.env_local` is loaded, and no existing broker or container is stopped.

Prerequisites: `mosquitto` on `PATH` and the Python dependencies from
`requirements-dev.txt` installed in `.venv`.

Run explicitly from the repository root:

```sh
POLESTAR_MQTT_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/test_mqtt_broker.py -v
```

The normal `./run_tests.sh` run skips these four checks unless explicitly enabled.
Unit tests retain their network guard. The integration fixtures stop their own
broker processes even when a check fails; temporary configs, logs and inventories
are kept in pytest's temporary directory for diagnosis.

Coverage:

- A fresh subscriber receives retained telemetry and mapping values at QoS 1.
- Missing fields and removed mappings disappear from the broker after confirmed
  zero-length retained publications; `null` and empty strings remain values.
- Container status, credentials, endpoint diagnostics and foreign topics survive.
- A subscriber explicitly disconnects/reconnects and receives the retained state.
- After restarting a broker with persistence disabled, the next application
  one-shot run republishes unchanged values and diagnostics using the same inventory.
- The production LWT configuration publishes retained `offline` at QoS 1 after an
  explicitly started test worker is killed; normal application runs end `offline`.
- A NoData response preserves existing endpoint values; subsequent recovery to a
  valid empty response removes the obsolete values and resets diagnostics to `OK`.

This validates the current one-shot runtime. Automatic publisher reconnect,
continuous polling and status republishing after automatic reconnect remain separate
M6.3/M7 work; these tests do not claim to implement or accept that behavior.
