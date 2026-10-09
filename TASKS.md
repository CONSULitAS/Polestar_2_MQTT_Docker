# TASKS.md

## Migration auf die offizielle Data Portal API

Die detaillierte, sequenziell abgearbeitete Migration einschließlich des
containerisierten Auth-only-QS-Gates wird in
[`documentation/Migration-Tasks-Data-Portal-API.md`](documentation/Migration-Tasks-Data-Portal-API.md)
geführt. Bis zur dort vorgesehenen Umschaltung bleiben die stabilisierten
Legacy-Module `src/auth.py` und `src/graphql_queries.py` erhalten.

## Stabilisierungsmaßnahmen (Priorität)

- [ ] API-/GraphQL-Fehlerpfad in Notlauf überführen
  - Quelle: `src/Polestar_2_MQTT.py:11–13` (`better error handling`; API-Fehler über MQTT melden statt Abbruch nach `MAX_RETRIES`).
  - Kontext: Feldänderungen in GraphQL können aktuell komplette Abfragen brechen.
  - Ziel: bei API-Feldfehlern nicht abbrechen, `api_error` setzen, Teilbetrieb weiterlaufen lassen.
  - Akzeptanz: Container bleibt aktiv; Diagnose-Topics enthalten Fehlerursache.

- [ ] MQTT-Reconnect stabilisieren
  - Quelle: `src/Polestar_2_MQTT.py:9` (`reconnect to MQTT is not stable`).
  - Ziel: robustes Reconnect-Verhalten bei Broker-Ausfall/Restart.
  - Akzeptanz: automatischer Reconnect ohne manuellen Neustart über längere Laufzeit.

- [ ] Telemetrie-/Response-Validierung weiter härten
  - Kontext: Teilvalidierung vorhanden, aber noch nicht durchgängig für degradierte Teilantworten.
  - Ziel: konsistente defensive JSON-/Feldprüfung für alle API-Pfade.
  - Akzeptanz: keine ungefangenen Exceptions bei unvollständigen Antworten.

## Weitere Aufgaben

- [ ] OpenWB-Topic vollständig per ENV konfigurierbar machen
  - Quellen: `src/Polestar_2_MQTT.py:14` (`fix OPENWB_TOPIC to make it configurable in docker-compose.yml`) und `:117` (`use ENV string`).
  - Akzeptanz: Das vollständige Topic lässt sich über `OPENWB_TOPIC` in der Compose-Konfiguration setzen; der bisherige Standard bleibt verfügbar.
- [ ] Bedeutung und Restbedarf des Legacy-TODOs „openWB URL“ klären
  - Quelle: `src/Polestar_2_MQTT.py:10` (`openWB URL`).
  - Kontext: `OPENWB_HOST` und `OPENWB_PORT` sind bereits per ENV konfigurierbar; die Markierung benennt keine konkrete verbleibende Änderung.
  - Akzeptanz: Offenen Bedarf an der openWB-Zieladresse konkretisieren oder die Aufgabe nach Prüfung als bereits erfüllt abschließen; Topic-Konfiguration wird separat geführt.
- [ ] Logging strukturieren
- [ ] Weitere testbare Kernlogik aus `src/Polestar_2_MQTT.py` extrahieren

## Chronologischer Verlauf

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

## TODO-Abgleich

Am 09.10.2026 wurden alle sechs TODO-Markierungen im versionierten Code sowie
der anschließende Hinweis zur API-Fehlermeldung abgeglichen. Sie stehen sämtlich
in `src/Polestar_2_MQTT.py` und sind oben ohne doppelte offene Aufgaben erfasst.
Die TODO-Kommentare im Code bleiben unverändert. Die Erfassung beauftragt keine
zusätzlichen Legacy-Codeänderungen während der Data-Portal-Migration.
