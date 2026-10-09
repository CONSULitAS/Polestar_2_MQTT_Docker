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
  `select_openapi_file()` in `openapi_catalog.py` wählt die über
  `POLESTAR_OPENAPI_FILE` konfigurierte lokale Datei (Standard:
  `/local-files/Polestar_DataPortalAPI.json`), andernfalls den gebündelten Fallback.
  Relative lokale Pfade beziehen sich auf das Arbeitsverzeichnis; der gebündelte
  Pfad ist davon unabhängig. Eine leere ENV-Angabe verwendet den Standardpfad.
  Nur eine fehlende lokale Datei erlaubt den Fallback; Verzeichnisse, defekte
  Symlinks und Fehler beim Dateistatus-Zugriff werden ohne Pfadausgabe abgelehnt.
  Die Auswahl selbst lädt keine Inhalte und führt keine Downloads aus.
- `load_openapi_document()` liest die gewählte Datei als UTF-8-JSON (BOM erlaubt)
  und prüft OpenAPI `3.1.x`, `info.title`, `info.version`, nicht leere `paths`,
  Pfad-/Operations-/Antwortobjekte sowie den Objekttyp optionaler `components`.
  Doppelte JSON-Schlüssel und nicht standardkonforme Konstanten wie `NaN`
  werden abgelehnt. Eine ungültige lokale Datei löst keinen Fallback aus.
  Dies ist eine Grundstrukturprüfung, keine vollständige OpenAPI-Schemavalidierung.
- Der Data-Portal-Einmallauf lädt beim Start einmal vor HTTP und MQTT; ungültige
  Dateien führen zu Exit-Code 2 ohne Ausgabe von Dateiinhalten oder Pfaden.
  Der geladene Snapshot wird nicht automatisch aktualisiert; eine neue Datei
  wirkt erst beim nächsten Prozessstart. Auth-only- und SoC-Diagnose bleiben
  unabhängig. Der dauerhafte Start-/Polling-Ablauf und die Umstellung des
  Legacy-Container-Einstiegspunkts bleiben M7/M8 vorbehalten.
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
