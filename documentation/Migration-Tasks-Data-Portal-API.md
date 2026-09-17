# Tasks: Migration auf die offizielle Polestar Data Portal API

Diese Taskliste setzt das [MVP-Konzept](MVP-offizielle-Data-Portal-API.md) für Login und SoC-Abruf um. Die Reihenfolge berücksichtigt technische Abhängigkeiten. M8 liefert den funktionalen End-to-End-Nachweis; abgeschlossen ist die Migration nach der anschließenden Bereinigung in M9.

## M0 – API-Zugang und Annahmen verifizieren

**Priorität:** Blocker  
**Abhängigkeiten:** keine

- [x] Gültige `clientId`, `clientSecret`, Account-ID und autorisierte VIN bereitstellen.
- [x] Ablaufdatum des Client Secrets dokumentieren.
- [x] Klären, ob die dokumentierte Basis-URL der vorgesehene produktive Endpunkt oder nur eine Sandbox ist.
- [x] `POST /token` mit Scope `pdp-telemetry/battery` manuell testen.
- [x] `GET /v1/vehicles` mit Token und `x-client-id` testen.
- [x] Battery-Endpunkt mit einer autorisierten VIN testen.
- [x] Bestätigte Erfolgsantworten redigiert und Fehlerantworten schema-konform als Test-Fixtures festhalten; keine Credentials oder Tokens einchecken.

**Abnahme:** Token, Fahrzeugliste und SoC lassen sich mit den vorgesehenen Credentials abrufen; offene Abweichungen zur OpenAPI-Spezifikation sind dokumentiert.

**Smoke-Test vom 16.09.2026:** `/token`, `/v1/vehicles` und der Battery-Endpunkt antworteten jeweils mit HTTP 200. Der Token ist vom Typ `Bearer` und 3.600 Sekunden gültig. Ein Fahrzeug wurde als autorisiert gemeldet, die lokal konfigurierte VIN war darin enthalten und die Battery-Antwort enthielt einen numerischen SoC sowie einen Quellzeitstempel. Credentials, Token, VIN und Messwert wurden nicht im Dokument gespeichert.

**Endpunkt-Klassifizierung vom 17.09.2026:** Die bereitgestellte OpenAPI-Spezifikation bezeichnet die API ausdrücklich als „EU Data Act Developer Portal Sandbox“ und führt unter `servers` ausschließlich `https://pc-api.polestar.com/eu-north-1/data-portal/m2m` auf. Ein separater Produktions-Endpunkt ist nicht dokumentiert. Für den MVP wird daher dieser erfolgreich getestete, offiziell angegebene Sandbox-Endpunkt verwendet und über `POLESTAR_API_BASE_URL` konfigurierbar gehalten. Vor einem späteren Produktionsrelease ist erneut zu prüfen, ob Polestar einen separaten Produktions-Endpunkt veröffentlicht hat.

**Fixtures vom 17.09.2026:** Die beim erfolgreichen Smoke-Test bestätigten Antwortstrukturen für Token, Fahrzeugliste und Battery sind unter `tests/fixtures/data_portal` mit ausschließlich synthetischen Werten abgelegt. Die Fehler-Fixtures wurden ohne absichtlich ausgelösten Live-Fehler aus den OpenAPI-Fehlerschemas erzeugt und entsprechend gekennzeichnet. Es wurden keine echten Credentials, Tokens, VINs, Request-IDs oder Messwerte gespeichert.

## M1 – Projektstruktur und Testbasis vorbereiten

**Priorität:** Hoch  
**Abhängigkeiten:** keine

- [x] Zielstruktur mit getrennten Modulgrenzen für Konfiguration, Polestar-API, MQTT-Publisher und Programmsteuerung anlegen; die Implementierungen werden in M2 sowie M4–M7 schrittweise aus dem Monolithen übernommen.
- [x] Einen HTTP-Client über `requests.Session` kapseln.
- [x] Test-Framework und HTTP-Mocking in `src/requirements.txt` beziehungsweise separaten Development-Abhängigkeiten ergänzen.
- [x] Unit-Test-Struktur anlegen.
- [x] Sicherstellen, dass alle Tests ohne echten Netzwerkzugriff ausführbar sind.

**Abnahme:** Ein minimaler Testlauf funktioniert lokal und verändert das Laufzeitverhalten noch nicht.

**Upstream-Abgleich vom 17.09.2026:** Der zwischenzeitlich nach `main` aufgenommene
Legacy-Refactor (`src/auth.py`, `src/graphql_queries.py`, zentrale Tests unter `tests/`)
bleibt bis zur finalen Umschaltung erhalten. Die Data-Portal-Implementierung bleibt
im separaten Package `src/polestar_mqtt/`. Testkonfiguration und Dev-Abhängigkeiten
werden ausschließlich zentral über `pytest.ini` und `requirements-dev.txt` im
Repository-Root gepflegt.

## M2 – Neue Konfiguration implementieren

**Priorität:** Hoch  
**Abhängigkeiten:** M1

- [x] Neue Pflichtvariablen einführen:
  - [x] `POLESTAR_CLIENT_ID`
  - [x] `POLESTAR_CLIENT_SECRET`
  - [x] `POLESTAR_CLIENT_SECRET_EXPIRES_AT`
  - [x] `POLESTAR_ACCOUNT_ID`
  - [x] `POLESTAR_VIN`
- [x] `POLESTAR_API_BASE_URL` mit der dokumentierten M2M-URL als Default ergänzen.
- [x] Bestehende MQTT-, openWB-, Zeitzonen- und Polling-Konfiguration übernehmen.
- [x] Alle Pflichtwerte beim Start validieren.
- [x] VIN-Format, positives Polling-Intervall und Ablaufdatum im Portalformat `YYYY-MM-DD` validieren.
- [x] Ein Polling-Intervall unter 10 Sekunden ablehnen.
- [x] Secret und andere vertrauliche Werte in Fehlern und Logs redigieren.
- [x] Unit-Tests für gültige, fehlende und ungültige Konfiguration ergänzen.

**Abnahme:** Ungültige Konfiguration beendet den Start mit einer verständlichen Meldung; kein geheimer Wert erscheint im Log.

## M3 – Client-Secret-Ablauf überwachen

**Priorität:** Hoch  
**Abhängigkeiten:** M2

- [x] `POLESTAR_CLIENT_SECRET_EXPIRES_AT` zeitzonensicher in UTC parsen.
- [x] Das Portal-Datum `YYYY-MM-DD` beim Einlesen verbindlich um `00:00:00` und die über `TZ` konfigurierte Zeitzone ergänzen.
- [x] Verbleibende volle Tage berechnen.
- [x] Statusmodell implementieren:
  - [x] `ok`: mehr als 30 Tage
  - [x] `warning`: 30 bis 8 Tage
  - [x] `critical`: 7 Tage bis unmittelbar vor den Ablaufzeitpunkt
  - [x] `expired`: Ablaufzeitpunkt erreicht
- [x] Warnungen bei 30, 14, 7, 3, 1 und 0 Tagen erzeugen.
- [x] Warnungen je Schwelle während einer Prozesslaufzeit entprellen.
- [x] Credential-Status beim Start und danach mindestens täglich prüfen.
- [x] Unit-Tests für alle Status- und Warnschwellengrenzen ergänzen.

**Abnahme:** Ablaufstatus und Warnungen sind deterministisch testbar; das Client Secret selbst wird nie ausgegeben.

## M4 – OAuth2 TokenProvider implementieren

**Priorität:** Hoch  
**Abhängigkeiten:** M1, M2

- [x] `POST /token` mit `clientId`, `clientSecret` und minimalem Battery-Scope implementieren.
- [x] JSON- oder Form-Encoding bewusst auswählen und testen.
- [x] `accessToken`, `expiresIn` und `tokenType` validieren.
- [x] Token ausschließlich im Speicher halten.
- [x] Ablaufzeit monoton berechnen und 60 Sekunden Sicherheitsmarge berücksichtigen.
- [x] Vor Ablauf automatisch ein neues Token per Client-Credentials-Flow beziehen.
- [x] Keinen Refresh-Token-Flow implementieren.
- [x] Connect- und Read-Timeouts setzen.
- [x] Fehlerantworten redigiert in eigene Exception-Typen überführen.
- [x] Unit-Tests für Erfolg, ungültige Antwort, `400`, `401`, `500`, `502`, `503` und Timeout ergänzen.

**Abnahme:** Token werden wiederverwendet und rechtzeitig ersetzt; Secrets und Access Tokens erscheinen nicht im Log.

## M4A – Containerisierter Auth-only-QS-Check

**Priorität:** Blocker vor M5  
**Abhängigkeiten:** M2, M4

Dieser Zwischenstand weist die Anmeldung mit dem neu implementierten Code nach, bevor Fahrzeug- oder Telemetrie-Endpunkte entwickelt werden.

- [x] Einen separaten Einstiegspunkt `python -m polestar_mqtt.auth_check` implementieren.
- [x] Ausschließlich Konfiguration laden und `POST /token` über den neuen `TokenProvider` ausführen.
- [x] Keine Fahrzeug-, Battery-, MQTT- oder openWB-Verbindung aufbauen.
- [x] Bei Erfolg nur eine redigierte Zusammenfassung ausgeben: HTTP-Erfolg, Token-Typ und `expiresIn`; niemals Client Secret oder Access Token.
- [x] Für Erfolg Exit-Code 0 und für Konfigurations-, Authentifizierungs- oder Transportfehler einen Exit-Code ungleich 0 liefern.
- [x] Den Auth-only-Check lokal mit echten Credentials ausführen:

  ```sh
  ./run_local.sh auth-check
  ```

- [x] Den Check mit den lokalen, ignorierten Credentials containerisiert ausführen:

  ```sh
  docker compose build polestar2mqtt
  docker compose run --rm polestar2mqtt python -m polestar_mqtt.auth_check
  ```

- [x] Im Testprotokoll nur Zeitpunkt, Ergebnis, Token-Typ und Laufzeit festhalten.

**Abnahme:** Der neu gebaute Container bezieht mit den lokalen Credentials über den neuen Code erfolgreich einen Access Token und beendet sich mit Exit-Code 0, ohne einen fachlichen API-Endpunkt aufzurufen oder vertrauliche Werte auszugeben. Erst danach beginnt M5.

**Auth-only-QS-Nachweis vom 17.09.2026:** Das Image wurde lokal neu gebaut und
`python -m polestar_mqtt.auth_check` im Container mit den ignorierten lokalen
Credentials ausgeführt. Ergebnis: erfolgreich, Token-Typ `Bearer`, Laufzeit
3.600 Sekunden, Exit-Code 0. Es wurden weder Access Token noch Client Secret,
VIN oder fachliche Fahrzeugdaten ausgegeben; Fahrzeug-, Battery-, MQTT- und
openWB-Endpunkte wurden nicht aufgerufen.

Zusätzlich wurde derselbe Auth-only-Check außerhalb des Containers über
`./run_local.sh auth-check` mit `.env` und `.env_local` ausgeführt. Ergebnis:
erfolgreich, Token-Typ `Bearer`, Laufzeit 3.600 Sekunden, Exit-Code 0. Auch
dieser Lauf rief ausschließlich `POST /token` auf.

## M5 – Data-Portal-Client für Fahrzeuge und Battery implementieren

**Priorität:** Hoch  
**Abhängigkeiten:** M4A

- [x] Gemeinsame Header mit Bearer Token, `x-client-id` und `Accept: application/json` erzeugen.
- [x] `GET /v1/vehicles` implementieren.
- [x] Konfigurierte VIN gegen die autorisierte Fahrzeugliste prüfen.
- [x] `GET /v1/vehicles/{vin}/telemetry/battery` implementieren.
- [x] VIN als Pfadparameter sicher behandeln.
- [x] `data.batteryChargeLevelPercentage` extrahieren und als numerischen Wert von 0 bis 100 validieren.
- [x] Optionale bzw. fehlende Telemetriefelder korrekt behandeln.
- [x] Antwort-VIN gegen die konfigurierte VIN validieren.
- [x] Quellzeitstempel aus `data.timestamp.seconds` und `nanos` verarbeiten, sofern vorhanden.
- [x] Bei `401` genau einmal ein neues Token holen und den Request wiederholen.
- [x] `400`, `403`, `404`, `429`, `500` und `503` fachlich unterscheiden.
- [x] Exponentielles Backoff mit Jitter für temporäre Fehler vorsehen und `Retry-After` beachten.
- [x] Unit-Tests für alle Erfolgs-, Daten- und Fehlerfälle ergänzen.

**Abnahme:** Eine autorisierte VIN liefert einen validierten SoC; ungültige oder fehlende Daten werden nicht als erfolgreicher Messwert ausgegeben.

**M5-QS-Nachweis vom 17.09.2026:** Ruff und die vollständige automatisierte
Testsuite liefen mit 138 erfolgreichen Tests durch. Der sichere SoC-Check wurde
anschließend lokal und mit dem frisch gebauten Container gegen die Data Portal
API ausgeführt. Beide Läufe bestätigten eine autorisierte VIN und denselben, am
realen Fahrzeug verifizierten SoC. Credentials, Token, VIN und Messwert werden
in diesem Nachweis nicht gespeichert.

## M6 – MQTT- und openWB-Ausgabe migrieren

**Priorität:** Hoch  
**Abhängigkeiten:** M3, M5

- [ ] Erfolgreiche Data-Portal-JSON-Antworten rekursiv in MQTT-Topics auflösen; Objektpfade bilden dabei automatisch die Topic-Struktur.
- [ ] Neue oder bislang unbekannte Telemetriefelder ohne Codeänderung automatisch publizieren.
- [ ] Topic-Segmente aus JSON-Schlüsseln deterministisch und MQTT-sicher normalisieren.
- [ ] Skalare JSON-Werte retained mit QoS 1 publizieren; Objekte und Arrays rekursiv behandeln.
- [ ] Eine optionale lokale Mapping-Datei für zusätzliche Topics einführen und über `local-files` in den Container einbinden.
- [ ] Das Mapping ordnet einen JSON-Quellpfad einer Liste aus einem oder mehreren Ziel-Topics zu.
- [ ] Relative Mapping-Ziele unterhalb von `MQTT_BASE_TOPIC` und ausdrücklich absolute Ziel-Topics unterstützen.
- [ ] Mapping-Ziele zusätzlich zu den dynamisch erzeugten Topics publizieren; sie dürfen die dynamische Ausgabe weder ersetzen noch unterdrücken.
- [ ] Fehlende Mapping-Datei als gültige Standardkonfiguration behandeln; ungültige Einträge mit verständlichen, redigierten Meldungen ablehnen.
- [ ] Eine versionierte Mapping-Beispieldatei bereitstellen.
- [ ] Die zuletzt erfolgreich publizierte Menge der verwalteten dynamischen und Mapping-Topics in einer lokalen Zustandsdatei außerhalb des Containers persistieren.
- [ ] Die Zustandsdatei über `local-files` dauerhaft in den Container einbinden und atomar aktualisieren, damit Container-Neustarts die Topic-Historie nicht verlieren.
- [ ] Nach einem erfolgreichen API-Abruf die zuvor persistierten Topics mit der aktuell erzeugten Topic-Menge vergleichen.
- [ ] Nicht mehr erzeugte verwaltete Topics mit einem leeren retained Publish (Zero-Length-Payload) und QoS 1 aus dem Broker löschen.
- [ ] Die neue Topic-Menge erst persistieren, nachdem alle aktuellen Publishes und erforderlichen Lösch-Publishes erfolgreich bestätigt wurden.
- [ ] Ausschließlich vom Telemetrie-Publisher verwaltete dynamische und Mapping-Topics löschen; Containerstatus-, Credential- und fremde Topics niemals aus dem Inventar ableiten oder entfernen.
- [ ] Den Namespace `<base>/container/+` als stabile, separat verwaltete Betriebs- und Statusschnittstelle beibehalten; ihn weder dynamisch aus API-JSON erzeugen noch in das persistierte Telemetrie-Topic-Inventar aufnehmen.
- [ ] Mapping-Ziele unterhalb von `<base>/container/+` ablehnen, damit lokale Mappings die Betriebs- und Statusschnittstelle nicht überschreiben können.
- [ ] Den bisherigen kompatiblen SoC-Topic über die Mapping-Schicht als zusätzliche Ausgabe ermöglichen:
  - [ ] `<base>/carTelematics/battery/batteryChargeLevelPercentage`
- [ ] Bestehendes LWT unter `<base>/container/connected` beibehalten.
- [ ] `<base>/container/last_update` nur nach erfolgreichem Battery-Abruf aktualisieren.
- [ ] Redigierten Fehlerstatus unter `<base>/container/last_error` bereitstellen.
- [ ] Bestehendes `<base>/container/last_exception` beibehalten und ausschließlich redigierte technische Fehlerinformationen publizieren.
- [ ] Quellzeitstempel optional unter `<base>/carTelematics/battery/sourceTimestamp` publizieren.
- [ ] Credential-Überwachung retained publizieren:
  - [ ] `<base>/container/credentials/client_secret_expires_at`
  - [ ] `<base>/container/credentials/client_secret_days_remaining`
  - [ ] `<base>/container/credentials/client_secret_status`
- [ ] Change Detection für SoC beibehalten.
- [ ] openWB nur mit vorhandenem, validiertem SoC aktualisieren.
- [ ] Tests mit gemocktem MQTT-Client für rekursive dynamische Topics, neue JSON-Felder, Mapping auf mehrere Ziele, fehlende und ungültige Mapping-Dateien, persistiertes Topic-Inventar, verwaiste retained Topics, Payload, QoS und Retain ergänzen.

**Abnahme:** Die MQTT-Ausgabe bildet die gelieferte JSON-Struktur ohne fest codierte
Telemetriefeldliste dynamisch ab. Lokale Mappings können denselben Quellwert in
mehrere zusätzliche Topics schreiben und damit bestehende Node-RED-, openWB-
oder andere Zielsysteme versorgen, ohne die dynamischen Standard-Topics zu
verändern. Nach Container-Neustarts werden nicht mehr erzeugte, zuvor vom
Telemetrie-Publisher verwaltete retained Topics zuverlässig aus dem Broker
entfernt. Die bestehende `<base>/container/+`-Schnittstelle bleibt stabil und
wird gezielt um neue Betriebsfunktionen wie den Credential-Status ergänzt.

## M7 – Polling, Fehlerbehandlung und Shutdown überarbeiten

**Priorität:** Hoch  
**Abhängigkeiten:** M5, M6

- [ ] Startreihenfolge festlegen: Konfiguration, MQTT, Credential-Status, Token, VIN-Prüfung, Polling.
- [ ] Das bisherige `wait_and_die()` entfernen.
- [ ] Temporäre API-Fehler ohne Prozessende behandeln.
- [ ] Permanente Konfigurations- und Berechtigungsfehler klar kennzeichnen und mit langsamem Retry behandeln, sofern MQTT-Status beobachtbar bleiben soll.
- [ ] Eine enge Docker-Restart- oder Token-Request-Schleife verhindern.
- [ ] SIGTERM-Verarbeitung und MQTT-Disconnect beibehalten bzw. testen.
- [ ] Systemzeitänderungen dürfen die Access-Token-Frist nicht verfälschen; monotone Zeit verwenden.
- [ ] Integrationstests für mehrere Polling-Zyklen, Token-Erneuerung und Fehlererholung ergänzen.

**Abnahme:** Der Dienst läuft nach temporären HTTP- und MQTT-Problemen weiter und beendet sich bei SIGTERM sauber.

## M8 – Container, Deployment und Dokumentation migrieren

**Priorität:** Hoch  
**Abhängigkeiten:** M2–M7

- [ ] `docker-compose_example.yml` auf die neuen Variablen und sichere Platzhalter umstellen.
- [ ] `POLESTAR_EMAIL` und `POLESTAR_PASSWORD` aus der Deployment-Vorlage entfernen.
- [ ] `README.md` mit Credential-Erstellung, Secret-Ablaufdatum, Migration und MQTT-Vertrag aktualisieren.
- [ ] `Synology-howto.md` aktualisieren.
- [ ] Lokale, ignorierte `docker-compose.yml` für den E2E-Test anpassen.
- [ ] Docker-Image lokal bauen und automatisierte Tests darin ausführen.
- [ ] Multi-Arch-Build im Workflow `.github/workflows/docker-image.yml` verifizieren.
- [ ] End-to-End-Test mit echten Credentials, MQTT und optional openWB durchführen.
- [ ] In Logs und MQTT prüfen, dass weder Client Secret noch Access Token vorkommen.

**Abnahme:** Das neue Image startet anhand der versionierten Beispielkonfiguration; Login, VIN-Prüfung, SoC-MQTT-Publikation und Ablaufwarnung funktionieren im E2E-Test.

## M9 – Alten API-Code entfernen und Migration abschließen

**Priorität:** Hoch  
**Abhängigkeiten:** erfolgreicher M8-End-to-End-Test

- [ ] Polestar-ID-, PKCE- und Benutzer-Login-Code entfernen.
- [ ] Refresh-Token-Code entfernen.
- [ ] GraphQL-Requests an `mystar-v2` entfernen.
- [ ] Nicht mehr benötigte Imports und Abhängigkeiten entfernen.
- [ ] Veraltete Umgebungsvariablen aus allen Dokumenten entfernen.
- [ ] Optional beim Start eine eindeutige Fehlermeldung für noch gesetzte Altvariablen ausgeben.
- [ ] Gesamte Testsuite, Linter und Docker-Build ausführen.
- [ ] Release Notes mit Breaking Changes und Migrationsanleitung erstellen.

**Abnahme:** Zur Laufzeit existiert keine Abhängigkeit mehr von der inoffiziellen API; Tests, Image-Build und E2E-Test sind erfolgreich.

## Nicht Teil dieses MVP

- weitere Telemetriedomänen wie Odometer, Location, Exterior oder Health
- Charging-Schreiboperationen
- Delegation über `x-delegated-account-id`
- automatische Erstellung oder Rotation des Client Secrets
- persistente Speicherung bereits ausgegebener Ablaufwarnungen
- automatische Auswahl einer VIN bei mehreren Fahrzeugen
