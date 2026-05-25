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

## Task-Tracking
- Projektaufgaben und Status werden in `TASKS.md` gepflegt: siehe [TASKS.md](TASKS.md).

## Arbeitsrichtlinien für Mitwirkende
- Kleine, nachvollziehbare Änderungen mit klarer Commit-Beschreibung.
- Keine Credentials, Tokens oder VINs in Code, Logs oder Commits.
- KI-Agenten führen nach jeder Code-Anpassung automatisch die fachlich passenden Tests aus und berücksichtigen das Ergebnis bei weiteren Änderungen.
- Für Python-Unit-Tests ist standardmäßig `./run_tests.sh` zu verwenden; bei Änderungen mit Einfluss auf bestehende Tests oder testbare Kernlogik soll dieser Lauf nicht ausgelassen werden.
- Wenn Tests nicht ausgeführt werden können oder fehlschlagen, muss der KI-Agent dies transparent benennen und die Arbeit nicht als vollständig verifiziert darstellen.
- Bei API-/Login-Änderungen immer zuerst lokal testen (`./run_local.sh`) und danach im Container gegenprüfen.
- Bei Änderungen an MQTT-Topics auf Rückwärtskompatibilität achten (bestehende Dashboards/Node-RED-Flows).

## Definition of Done (DoD)
- Anwendung startet ohne Fehler (lokal oder via Docker).
- Relevante automatisierte Tests wurden ausgeführt; insbesondere nach Codeänderungen mindestens `./run_tests.sh`, sofern die Änderung nicht nachweislich außerhalb des Testumfangs liegt.
- MQTT-Verbindung wird aufgebaut und LWT-Status wird publiziert.
- Polestar-Login und Datenabfrage laufen stabil über mindestens einen Zyklus.
- Doku (`README`/`doc/`) ist für geänderte Bereiche aktualisiert.
