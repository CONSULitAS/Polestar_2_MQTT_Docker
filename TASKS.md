# TASKS.md

## Migration auf die offizielle Data Portal API

Die detaillierte, sequenziell abgearbeitete Migration einschließlich des
containerisierten Auth-only-QS-Gates wird in
[`documentation/Migration-Tasks-Data-Portal-API.md`](documentation/Migration-Tasks-Data-Portal-API.md)
geführt. Der alte Polestar-ID-/GraphQL-Code wurde auf Nutzerauftrag entfernt.
Die regulären Startwege verwenden vorerst den Data-Portal-Einmallauf.

## Offene Laufzeitaufgaben

- [ ] Dauerhaftes Polling, Fehlererholung und sauberes Herunterfahren (M7).
- [ ] Automatischen MQTT-Reconnect und Wiederveröffentlichung im Dauerbetrieb umsetzen; Container-Status und LWT im Einmallauf sind abgeschlossen.
- [ ] Docker-HEALTHCHECK implementieren und im Dockerfile einbinden.
- [ ] Separate OpenWB-Weiterleitung einschließlich konfigurierbarem Ziel-Topic umsetzen.
- [ ] Telemetrie-/Response-Validierung und strukturierte Diagnose weiter härten.
- [ ] Container-/Release-Abnahme gemäß M8/M8A/M9 abschließen.

## Chronologischer Verlauf

- [x] 2026-10-10: Betriebsstatus und Offline-LWT im Einmallauf umgesetzt: gültiger Battery-Abrufzeitpunkt, redigierte Fehlercodes und Exception-Typen sowie Credential-Status. Ruff und 414 Unit-Tests, vier MQTT-Integrationstests einschließlich LWT nach Prozessabbruch und lokaler API-/MQTT-Lauf mit 278 bestätigten Publishes erfolgreich. Dauerlauf-Integration separat offen.

- [x] 2026-10-10: Separaten MQTT-Testbroker-Nachweis für den Einmallauf ergänzt und bestanden: drei Mosquitto-Integrationstests für retained Werte, Löschungen, geschützte Topics, Subscriber-Reconnect, Broker-Neustart und NoData-Erholung. Ruff und 405 Unit-Tests erfolgreich; lokaler API-/MQTT-Lauf bestätigt. Automatischer Publisher-Reconnect im Dauerbetrieb bleibt offen.

- [x] 2026-10-10: Container-Persistenzabnahme für M6.2 auf Commit `50d86d7` bestanden: UID-999-Schreibrechte, atomare Speicherung, Neustart, Sperre zwischen Containern, Wiederaufnahme nach SIGKILL und unverändertes Inventar bei schreibgeschütztem Mount. Letzten M6.2-Punkt geschlossen; separater Testbroker-Nachweis in M6.4 bleibt offen.

- [x] 2026-10-10: Retained-Bereinigung im Einmallauf umgesetzt: gebundenes Inventar v3, bestätigte Löschungen, Wiederaufnahme offener Vorgänge und Schutz von Diagnose-/Container-Topics. Ruff und 405 Tests erfolgreich; lokaler API-/MQTT-Lauf mit 270 bestätigten Publishes und einem NoData-Endpunkt. Erledigte M6.2-/QS-Aufgaben geschlossen; Container-Persistenzabnahme und Testbroker-Integration bleiben separat offen.

- [x] 2026-10-10: Aufgabenstatus der endpunktbezogenen MQTT-Diagnose korrigiert: Ausgabe und Schutzmechanismen im Einmallauf abgeschlossen; verbleibenden Schutz bei Retained-Bereinigung (M6.2) und Polling-Integration (M7) als separate offene Aufgaben erfasst.

- [x] 2026-10-10: HTTP-Fehlerausgaben um den betroffenen Endpunktpfad ergänzt; Fahrzeugkennung und Query-Parameter bleiben verborgen.

- [x] 2026-10-10: Legacy-Laufzeit, GraphQL-Schema/-Vorlage, alte Tests und Node-RED-Beispiel mit `git rm` entfernt. Startwege auf den Data-Portal-Einmallauf umgestellt; Löschdirektive in `AGENTS.md` verschärft. Alte Extraktions-/Login-TODOs entfallen, verbleibende Laufzeitaufgaben sind oben erfasst.

- [x] 2026-10-09: Beim TODO-Abgleich bestätigt: Legacy-TODO `report online/offline state on MQTT (DONE)` (`src/Polestar_2_MQTT.py:12`) ist bereits umgesetzt (Online-Meldung und Offline-LWT); durch die frühere MQTT-Statuserweiterung abgedeckt.
- [x] 2026-05-11 bis 2026-05-25: Lokale Laufzeit-/Konfigurationsführung überarbeitet.
- [x] 2026-04-30 bis 2026-05-25: MQTT-Status und Diagnose erweitert.
- [x] 2026-04-30 bis 2026-05-25: Auth- und Token-Fehlerbehandlung gehärtet.
- [x] 2026-04-24 bis 2026-05-25: GraphQL/API-Felder an API-Änderungen angepasst.
- [x] 2026-05-11: Test-Infrastruktur eingeführt.
- [x] 2026-04-30: Authentifizierung aus dem Monolith ausgelagert.
- [x] 2026-04-21: Lokale GraphQL-Overrides für Container-Betrieb eingeführt.
- [x] 2026-04-21: Projektbasis für Agenten und Doku eingeführt.
- [x] 2026-04-20: Einstiegspunkt abgesichert und GraphQL-Payloads aus dem Hauptskript ausgelagert.
