# TASKS.md

## Aufgabenstatus (Stand 2026-05-25)

- [x] Authentifizierung in `src/auth.py` gekapselt (inkl. Refresh/Login-Fallback)
- [x] MQTT-Statusmodell erweitert: `online`, `auth_error`, `token_error`
- [x] Diagnose-Topics ergänzt
- [x] `.../container/last_error` (Fehlermeldung)
- [x] `.../container/last_exception` (Exception-Text)

## Backlog

- [x] Task 1: Robustere Fehlerbehandlung im Login-Flow
  - Kontext: `perform_login()` enthält Sonderpfad bei fehlendem `code`.
  - Ziel: Defensive Behandlung von Header-/Redirect-Varianten, klarere Fehlermeldungen auf MQTT.
  - Akzeptanz: Keine ungefangenen Exceptions bei unerwarteten Login-Antworten.
  - Umgesetzt: defensives `Location`-/Query-Parsing, abgesicherter `uid`-Follow-up, erweiterte Tests.

- [ ] Task 2: MQTT-Reconnect stabilisieren
  - Kontext: Im Code ist ein TODO zur instabilen Reconnect-Logik vorhanden.
  - Ziel: Reconnect-Verhalten unter Broker-Ausfall reproduzierbar und robust machen.
  - Akzeptanz: Nach Broker-Restart reconnectet der Dienst ohne manuellen Neustart.

- [ ] Task 3: OpenWB-Topic konfigurierbar machen
  - Kontext: `OPENWB_TOPIC` ist aktuell nicht per ENV konfigurierbar (TODO im Code).
  - Ziel: Vollständige ENV-Steuerung inkl. Topic-Template.
  - Akzeptanz: Topic kann ohne Codeänderung via Compose/ENV gesetzt werden.

- [ ] Task 4: Strukturierte Logs / Diagnostik verbessern
  - Kontext: Derzeit hauptsächlich `print()`-basiertes Logging.
  - Ziel: Log-Kontext (Zeit, Modul, Fehlerursache) verbessern.
  - Akzeptanz: Fehlerfälle lassen sich über Container-Logs schnell eingrenzen.

- [ ] Task 5: Testbare Kernlogik extrahieren
  - Kontext: Viele Funktionen liegen im Monolith-Skript.
  - Ziel: API- und MQTT-nahe Hilfslogik modularisieren, um Unit-Tests zu ermöglichen.
  - Akzeptanz: Weitere automatisierte Tests für extrahierte Module vorhanden.

## Nächste Schritte (Empfohlen)

- [x] Task 1 abgeschlossen
- [ ] Task 2 priorisieren (Betriebsstabilität)
- [ ] Danach Task 3 für Konfigurierbarkeit und Nutzerfreundlichkeit
- [ ] Anschließend Task 4/5 für Wartbarkeit
