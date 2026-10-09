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
3. Zielzustand: Die gebündelte oder lokal aktualisierte OpenAPI-Datei wird beim
   Containerstart einmal validiert. Ausschließlich erlaubte Fahrzeug-GET-Pfade
   bilden zusammen mit ihren Scopes den Endpoint-Katalog; die konfigurierte
   API-Basis bleibt unabhängig von `servers` in der Datei maßgeblich. Änderungen
   der Datei werden erst nach einem Container-Neustart übernommen.
4. OAuth2 Client Credentials fordern ein Token mit den aggregierten Scopes der
   aktivierten Endpunkte an; `/v1/vehicles` validiert die konfigurierte VIN.
5. Der Client arbeitet den Endpoint-Katalog sequenziell ab. Fehler bleiben auf
   den jeweiligen Endpunkt begrenzt.
6. Erfolgreiche JSON-Antworten werden unter einer vom API-Pfad abgeleiteten
   MQTT-Wurzel dynamisch publiziert. Optionale CSV-Mappings ergänzen weitere
   Ziel-Topics, ohne den dynamischen Baum zu ersetzen.
7. Der Battery-SoC erhält zusätzliche Fachvalidierung und kann optional an
   OpenWB weitergeleitet werden.

## Erweiterungspunkte
- Anpassbare GraphQL-Queries über `local-files/graphql_queries.py`
- Aktualisierbare OpenAPI-Spezifikation über
  `local-files/Polestar_DataPortalAPI.json` mit gebündeltem Fallback unter `api/`
- Zusätzliche lokale MQTT-Ziele über `local-files/mqtt_topic_mapping.csv`
- ENV-gesteuerte MQTT-/OpenWB-Parameter via Docker Compose

## Grenzen der OpenAPI-Steuerung
- Die versionierte Spezifikation liegt unter `api/Polestar_DataPortalAPI.json`
  und wird beim Image-Build nach `/app/api/Polestar_DataPortalAPI.json` kopiert.
  Das Laden und die Auswahl des lokalen Overrides werden erst in den folgenden
  M5B-Schritten implementiert.
- Automatisch übernommen werden nur kompatible `GET`-Operationen unter den
  freigegebenen Telemetrie- und Charging-Pfaden.
- Token- und Fahrzeuglistenabruf sowie VIN-, SoC- und Sicherheitsvalidierung
  bleiben explizite Programmlogik.
- Änderungen an Authentifizierung, HTTP-Methoden oder inkompatiblen
  Antwortverträgen erfordern weiterhin Codeänderungen.
- Eine lokale Spezifikation wird nicht automatisch aus dem Internet geladen und
  darf weder die Basis-URL noch beliebige neue Request-Ziele einschleusen.

## Migrationsgrenze
- Upstream-Änderungen am bisherigen Login bleiben in `src/auth.py` erhalten.
- Die offizielle API wird getrennt im Package `src/polestar_mqtt/` implementiert.
- Beide Testbereiche werden über die zentrale Root-Konfiguration `pytest.ini` ausgeführt.
- Erst nach erfolgreichem Container-QS-Check wird der Docker-Einstiegspunkt umgestellt.

## Bekannte technische Schwerpunkte
- Reconnect-Verhalten bei MQTT-Ausfällen
- Fehlerbehandlung im Auth-/Redirect-Flow
- Konfigurierbarkeit des OpenWB-Topics
