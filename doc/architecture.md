# Architektur

## Überblick
Das Projekt verbindet die Polestar-Cloud-API mit einem lokalen MQTT-Broker.

## Komponenten
- Offizielle Polestar Data Portal M2M API (`pc-api.polestar.com`)
- Legacy-Laufzeit während der Migration (`src/Polestar_2_MQTT.py`, `src/auth.py`,
  `src/graphql_queries.py`)
- Neue Data-Portal-Laufzeit (`src/polestar_mqtt/`)
- MQTT-Broker (z. B. Mosquitto)
- Optional: OpenWB v1 MQTT-Endpoint

## Datenfluss
1. Dienst liest ENV-Konfiguration.
2. Während der Migration: Login gegen Polestar ID und GraphQL-Aufrufe über den
   bestehenden Einstiegspunkt.
3. Zielzustand: OAuth2 Client Credentials und REST-Telemetrie über
   `src/polestar_mqtt/`; der Wechsel erfolgt erst nach dem Auth-only-QS-Gate M4A.
4. Veröffentlichung der Fahrzeugdaten auf MQTT-Topics unter `MQTT_BASE_TOPIC`.
5. Optionales Weiterleiten des SoC an OpenWB.

## Erweiterungspunkte
- Anpassbare GraphQL-Queries über `local-files/graphql_queries.py`
- ENV-gesteuerte MQTT-/OpenWB-Parameter via Docker Compose

## Migrationsgrenze
- Upstream-Änderungen am bisherigen Login bleiben in `src/auth.py` erhalten.
- Die offizielle API wird getrennt im Package `src/polestar_mqtt/` implementiert.
- Beide Testbereiche werden über die zentrale Root-Konfiguration `pytest.ini` ausgeführt.
- Erst nach erfolgreichem Container-QS-Check wird der Docker-Einstiegspunkt umgestellt.

## Bekannte technische Schwerpunkte
- Reconnect-Verhalten bei MQTT-Ausfällen
- Fehlerbehandlung im Auth-/Redirect-Flow
- Konfigurierbarkeit des OpenWB-Topics
