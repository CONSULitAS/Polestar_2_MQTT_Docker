# TASKS.md

## Backlog (Initial)

1. Robustere Fehlerbehandlung im Login-Flow
- Kontext: `perform_login()` enthält TODOs und Sonderpfad bei fehlendem `code`.
- Ziel: Defensive Behandlung von Header-/Redirect-Varianten, klarere Fehlermeldungen auf MQTT.
- Akzeptanz: Keine ungefangenen Exceptions bei unerwarteten Login-Antworten.

2. MQTT-Reconnect stabilisieren
- Kontext: Im Code ist ein TODO zur instabilen Reconnect-Logik vorhanden.
- Ziel: Reconnect-Verhalten unter Broker-Ausfall reproduzierbar und robust machen.
- Akzeptanz: Nach Broker-Restart reconnectet der Dienst ohne manuellen Neustart.

3. OpenWB-Topic konfigurierbar machen
- Kontext: `OPENWB_TOPIC` ist aktuell nicht per ENV konfigurierbar (TODO im Code).
- Ziel: Vollständige ENV-Steuerung inkl. Topic-Template.
- Akzeptanz: Topic kann ohne Codeänderung via Compose/ENV gesetzt werden.

4. Strukturierte Logs / Diagnostik verbessern
- Kontext: Derzeit hauptsächlich `print()`-basiertes Logging.
- Ziel: Log-Kontext (Zeit, Modul, Fehlerursache) verbessern.
- Akzeptanz: Fehlerfälle lassen sich über Container-Logs schnell eingrenzen.

5. Testbare Kernlogik extrahieren
- Kontext: Viele Funktionen liegen im Monolith-Skript.
- Ziel: API- und MQTT-nahe Hilfslogik modularisieren, um Unit-Tests zu ermöglichen.
- Akzeptanz: Erste automatisierte Tests für Token-/Payload-Helfer vorhanden.

## Nächste Schritte (Empfohlen)
1. Task 1 und 2 priorisieren (Betriebsstabilität).
2. Danach Task 3 für Konfigurierbarkeit und Nutzerfreundlichkeit.
3. Anschließend Task 4/5 für Wartbarkeit.
