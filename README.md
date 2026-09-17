# Polestar_2_MQTT_Docker
Docker Container with gateway between Polestar API and MQTT

Credits to Niklas Vieth (@hniklasvieth) for the great work on the Polestar SoC iOS Medium Widget (https://github.com/niklasvieth/polestar-ios-medium-widget).

This Software is based on this work and partly made with ChatGPT 4.0.

The initial prompt for ChatGPT was taken from @demichve on the German Polestar Forum (https://polestar.fans/t/soc-medium-homescreen-widget-ios/17121/41?u=consulitas). Just because this was currently running on my phone. :-)

If ChatGPT has been involved in development steps here, this will be shown in the comments to corresponding commits in this repository.

Heads up: This is work in progress, but now usable.
* Pull requests welcome!
* Issues welcome!

## Configuration files

This project now uses two local env files:

* `.env`: shared credentials and sensitive values for Docker Compose and `run_local.sh`
* `.env_local`: local runtime values used by `run_local.sh`

Both files are ignored by git. Versionable templates are provided as `.env.example` and `.env_local.example`.

### `.env`

Used by:
* `docker compose`
* `./run_local.sh`

Typical content:

```env
POLESTAR_ACCOUNT_ID="12345678-1234-1234-1234-123456789abc"
POLESTAR_CLIENT_ID="your-client-id"
POLESTAR_CLIENT_SECRET="your-client-secret"
POLESTAR_CLIENT_SECRET_EXPIRES_AT="2099-12-31"
POLESTAR_VIN="LPSVS000000000000"

# Temporary legacy login used until the Data Portal runtime is activated
POLESTAR_EMAIL="you@example.com"
POLESTAR_PASSWORD="your-polestar-password"

MQTT_USER=""
MQTT_PASSWORD=""
```

Notes:
* keep `MQTT_USER` and `MQTT_PASSWORD` empty if your broker has no login
* use the portal's `YYYY-MM-DD` format for `POLESTAR_CLIENT_SECRET_EXPIRES_AT`
* `.env.example` temporarily also contains the legacy email/password fields required by
  `run_local.sh`; they will be removed when the Data Portal runtime becomes the main entry point

#### Register and obtain Data Portal credentials

1. Open the [Polestar Data Portal](https://data-portal.polestar.com/) and sign in or complete the
   registration offered by the portal.
2. Open the API credentials area. The documentation is available at
   [API Documentation](https://data-portal.polestar.com/de/api-credentials/docs).
3. In the **API Documentation** tab, copy **Account ID / x-client-id** to
   `POLESTAR_ACCOUNT_ID`.
4. In the **API Credential** tab, generate a client credential.
5. Copy **App client ID** to `POLESTAR_CLIENT_ID` and **Client secret** to
   `POLESTAR_CLIENT_SECRET`.
6. Copy the date shown as **Expires on YYYY-MM-DD (90 days)** to
   `POLESTAR_CLIENT_SECRET_EXPIRES_AT`. Generate a replacement credential before this date.
7. Enter the vehicle's 17-character VIN as `POLESTAR_VIN`.

The App client ID identifies the API application. The Account ID is a separate value used as the
required `x-client-id` header for vehicle and telemetry requests.

### `.env_local`

Used by:
* `./run_local.sh`

Typical content:

```env
TZ="Europe/Berlin"
POLESTAR_CYCLE="270"
MQTT_BROKER="mqtt.example.local"
MQTT_PORT="1883"
MQTT_BASE_TOPIC="polestar2"
OPENWB_HOST="openwb.example.local"
OPENWB_PUBLISH="True"
OPENWB_PORT="1883"
OPENWB_LP_NUM="1"
```

Notes:
* this file is only needed for local non-container execution
* adjust `OPENWB_*` values only if you want direct forwarding to OpenWB v1

## GraphQL overrides

The container now mounts `./local-files` to `/local-files`.

If `/local-files/graphql_queries.py` exists inside the container, the app prefers that file over the built-in [src/graphql_queries.py](/home/hi345gr/Docker/Polestar_2_MQTT_Docker/src/graphql_queries.py). This lets you customize GraphQL queries without modifying the shipped source code.

Included template:
* [local-files/graphql_queries.py_sample](/home/hi345gr/Docker/Polestar_2_MQTT_Docker/local-files/graphql_queries.py_sample)

Usage:
1. copy `local-files/graphql_queries.py_sample` to `local-files/graphql_queries.py`
2. adjust the queries or payload builders as needed
3. restart the container

Keep the function names `build_getconsumercarsv2_payload()` and `build_cartelematicsv2_payload(vin)` unchanged, because the main program imports exactly these names.

## Docker startup

1. install Docker: https://docs.docker.com/engine/install/
2. download `docker-compose_example.yml`
3. rename it to `docker-compose.yml` (remove `_example`)
4. create `.env` from `.env.example`
5. optionally create `local-files/graphql_queries.py` from `local-files/graphql_queries.py_sample`
6. edit the remaining values under `environment:` in `docker-compose.yml`
7. start the container with `docker compose up` or `docker compose up -d`

The compose setup mounts `./local-files` into the container automatically.

## Local startup

1. create `.env` from `.env.example`
2. create `.env_local` from `.env_local.example`
3. adjust both files to your environment
4. run `./run_local.sh`

`run_local.sh` creates `.venv` if needed, installs Python dependencies, and then starts the app locally.

For a single polling cycle without the endless loop, use:

```bash
./run_local.sh runonce
```

This is mainly intended for a local end-to-end check.

For an authentication-only development check against the official Data Portal API, use:

```bash
./run_local.sh auth-check
```

This mode only requests an OAuth token. It does not start the legacy application and does not
connect to vehicle, telemetry, MQTT, or openWB endpoints. `./run_auth_check.sh` remains available
as a convenience wrapper for the same mode.

For one Data Portal read followed by confirmed MQTT output, use:

```bash
./run_local.sh runonce-DataPortalAPI
```

This mode authenticates, checks vehicle authorization, validates Battery SoC and publishes the
complete current Battery response retained with QoS 1 under
`<MQTT_BASE_TOPIC>/telemetry/battery`. It exits successfully only after the broker acknowledges
every publication. The console reports only success and the topic count; credentials, tokens,
VIN and measurement values are not printed. The MQTT payload includes the API's vehicle data.

Local runs load `.env` and `.env_local`; the MQTT settings in `.env_local` must point to the
intended broker and test topic. Local runs do not read `docker-compose.yml`.
Optional JSON-path mappings are loaded from `local-files/mqtt_topic_mapping.csv`, or from
`MQTT_TOPIC_MAPPING_FILE` if set. Absolute mapping targets use their exact configured topic.
See [the mapping documentation](doc/README.md#data-portal-mapping-json-pfad-zu-zusätzlichem-mqtt-topic).

`./run_soc_check.sh`, `./run_local.sh soc-check`, and `python -m polestar_mqtt.soc_check`
are compatibility entry points for this same command and **now also publish to MQTT**.
The legacy `./run_local.sh runonce` remains separate. This intermediate command does not run
a polling loop, publish container status, delete old retained topics, or forward separately to
the openWB broker. It has been tested locally; container validation is deferred.

## Unit tests

Unit tests are based on `pytest` and mock all external dependencies such as the Polestar API and MQTT brokers.

Quick start:
1. run `./run_tests.sh`

This script creates or reuses `.venv`, installs the test dependencies from `requirements-dev.txt`, runs `pytest`, and then starts a local end-to-end check with `./run_local.sh runonce` when `.env` and `.env_local` are available.
If one of these files is missing, the end-to-end step is skipped with a clear message.

You can also call pytest directly:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Current focus of the test suite:
* auth and token handling in `src/auth.py`
* GraphQL payload builders in `src/graphql_queries.py`
* MQTT publishing helpers and API response parsing in `src/Polestar_2_MQTT.py`
* Data Portal configuration, credential expiry, and HTTP transport in `src/polestar_mqtt/`

Discussions (in german ) here:
https://polestar.fans/t/polestar-api-zu-mqtt-im-container/18589

## direct forwarding to OpenWB v1:
* set `OPENWB_HOST:    "ip/dns name of openWB"`
* set `OPENWB_PUBLISH: True`
* optionally set `OPENWB_PORT` and `OPENWB_LP_NUM` - if not set it defaults to port 1883 and 1 (which results in topic `openWB/set/lp/1/%Soc`)
