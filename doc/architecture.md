# Architektur

## Überblick
Das Projekt verbindet die Polestar-Cloud-API mit einem lokalen MQTT-Broker.

## Komponenten
- Polestar API (`pc-api.polestar.com`, Polestar ID)
- Python-Service (`src/Polestar_2_MQTT.py`)
- MQTT-Broker (z. B. Mosquitto)
- Optional: OpenWB v1 MQTT-Endpoint

## Datenfluss
1. Dienst liest ENV-Konfiguration.
2. Login gegen Polestar ID (PKCE-Flow) und Erhalt von Access-/Refresh-Token.
3. GraphQL-Requests gegen Polestar API.
4. Veröffentlichung der Fahrzeugdaten auf MQTT-Topics unter `MQTT_BASE_TOPIC`.
5. Optionales Weiterleiten des SoC an OpenWB.

## Erweiterungspunkte
- Anpassbare GraphQL-Queries über `local-files/graphql_queries.py`
- ENV-gesteuerte MQTT-/OpenWB-Parameter via Docker Compose

## Bekannte technische Schwerpunkte
- Reconnect-Verhalten bei MQTT-Ausfällen
- Fehlerbehandlung im Auth-/Redirect-Flow
- Konfigurierbarkeit des OpenWB-Topics
