# AGENTS.md

## Ziel des Projekts
Dieses Repository betreibt einen Docker-basierten Gateway zwischen der Polestar API und MQTT. Das Hauptskript liest Fahrzeugdaten (GraphQL via Polestar API) und veröffentlicht diese periodisch an einen MQTT-Broker. Optional wird der SoC zusätzlich an OpenWB v1 weitergereicht.

## Primäre Komponenten
- `src/Polestar_2_MQTT.py`: Hauptanwendung (Login, Token-Handling, API-Zugriffe, MQTT-Publishing)
- `src/graphql_queries.py`: Standard-GraphQL-Payloads
- `local-files/graphql_queries.py_sample`: Vorlage für lokale Query-Overrides
- `docker-compose.yml` / `docker-compose_example.yml`: Container-Betrieb
- `.env` und `.env_local`: Laufzeitkonfiguration

## Laufzeit- und Konfigurationsprinzipien
- Secrets und Zugangsdaten liegen in `.env` (nicht einchecken).
- Für lokalen Start wird zusätzlich `.env_local` verwendet.
- GraphQL-Queries sollen bevorzugt über `local-files/graphql_queries.py` angepasst werden (statt Core-Code zu patchen).
- Der Container mountet `./local-files` nach `/local-files`.

## Arbeitsrichtlinien für Mitwirkende
- Kleine, nachvollziehbare Änderungen mit klarer Commit-Beschreibung.
- Keine Credentials, Tokens oder VINs in Code, Logs oder Commits.
- Bei API-/Login-Änderungen immer zuerst lokal testen (`./run_local.sh`) und danach im Container gegenprüfen.
- Bei Änderungen an MQTT-Topics auf Rückwärtskompatibilität achten (bestehende Dashboards/Node-RED-Flows).

## Definition of Done (DoD)
- Anwendung startet ohne Fehler (lokal oder via Docker).
- MQTT-Verbindung wird aufgebaut und LWT-Status wird publiziert.
- Polestar-Login und Datenabfrage laufen stabil über mindestens einen Zyklus.
- Doku (`README`/`doc/`) ist für geänderte Bereiche aktualisiert.
