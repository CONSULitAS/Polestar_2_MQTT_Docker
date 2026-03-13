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
POLESTAR_EMAIL="you@example.com"
POLESTAR_PASSWORD="your-polestar-password"
POLESTAR_VIN="your-vin-without-spaces"
MQTT_USER=""
MQTT_PASSWORD=""
```

Notes:
* keep `MQTT_USER` and `MQTT_PASSWORD` empty if your broker has no login
* `POLESTAR_VIN` must not contain spaces

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

## Docker startup

1. install Docker: https://docs.docker.com/engine/install/
2. download `docker-compose_example.yml`
3. rename it to `docker-compose.yml` (remove `_example`)
4. create `.env` from `.env.example`
5. edit the remaining values under `environment:` in `docker-compose.yml`
6. start the container with `docker compose up` or `docker compose up -d`

No volumes or custom network are required.

## Local startup

1. create `.env` from `.env.example`
2. create `.env_local` from `.env_local.example`
3. adjust both files to your environment
4. run `./run_local.sh`

`run_local.sh` creates `.venv` if needed, installs Python dependencies, and then starts the app locally.

Discussions (in german ) here:
https://polestar.fans/t/polestar-api-zu-mqtt-im-container/18589

## direct forwarding to OpenWB v1:
* set `OPENWB_HOST:    "ip/dns name of openWB"`
* set `OPENWB_PUBLISH: True`
* optionally set `OPENWB_PORT` and `OPENWB_LP_NUM` - if not set it defaults to port 1883 and 1 (which results in topic `openWB/set/lp/1/%Soc`)
