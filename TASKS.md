# TASKS.md

## Stabilisierungsmaßnahmen (Priorität)

- [ ] API-/GraphQL-Fehlerpfad in Notlauf überführen
  - Kontext: Feldänderungen in GraphQL können aktuell komplette Abfragen brechen.
  - Ziel: bei API-Feldfehlern nicht abbrechen, `api_error` setzen, Teilbetrieb weiterlaufen lassen.
  - Akzeptanz: Container bleibt aktiv; Diagnose-Topics enthalten Fehlerursache.

- [ ] MQTT-Reconnect stabilisieren
  - Kontext: TODO im Code (`reconnect to MQTT is not stable`).
  - Ziel: robustes Reconnect-Verhalten bei Broker-Ausfall/Restart.
  - Akzeptanz: automatischer Reconnect ohne manuellen Neustart über längere Laufzeit.

- [ ] Telemetrie-/Response-Validierung weiter härten
  - Kontext: Teilvalidierung vorhanden, aber noch nicht durchgängig für degradierte Teilantworten.
  - Ziel: konsistente defensive JSON-/Feldprüfung für alle API-Pfade.
  - Akzeptanz: keine ungefangenen Exceptions bei unvollständigen Antworten.

## Weitere Aufgaben

- [ ] OpenWB-Topic vollständig per ENV konfigurierbar machen
- [ ] Logging strukturieren
- [ ] Weitere testbare Kernlogik aus `src/Polestar_2_MQTT.py` extrahieren

## Chronologischer Verlauf

- [x] 2026-04-20: Einstiegspunkt abgesichert und GraphQL-Payloads aus dem Hauptskript ausgelagert.
- [x] 2026-04-21: Projektbasis für Agenten und Doku eingeführt.
- [x] 2026-04-21: Lokale GraphQL-Overrides für Container-Betrieb eingeführt.
- [x] 2026-04-24 bis 2026-05-25: GraphQL/API-Felder an API-Änderungen angepasst.
- [x] 2026-04-30: Authentifizierung aus dem Monolith ausgelagert.
- [x] 2026-04-30 bis 2026-05-25: Auth- und Token-Fehlerbehandlung gehärtet.
- [x] 2026-04-30 bis 2026-05-25: MQTT-Status und Diagnose erweitert.
- [x] 2026-05-11: Test-Infrastruktur eingeführt.
- [x] 2026-05-11 bis 2026-05-25: Lokale Laufzeit-/Konfigurationsführung überarbeitet.
