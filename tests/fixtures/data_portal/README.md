# Polestar Data Portal API fixtures

These fixtures reproduce the response shapes confirmed by the live smoke test on 2026-09-16 without retaining real credentials, tokens, VINs, request IDs, timestamps, or telemetry values.

- `token_success.json`, `vehicles_success.json`, and `battery_success.json` use the response structures observed during the successful smoke test. Every value is synthetic or redacted.
- `oauth_error.json` and `m2m_error.json` follow the error schemas in `Polestar_DataPortalAPI.json`. No live error request was deliberately triggered; their values are synthetic.

The reserved VIN `LPSVS000000000000` and identifiers prefixed with `fixture-` must never be replaced with production data. Tests may load these files but must not modify them.
