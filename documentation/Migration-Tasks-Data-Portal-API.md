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
- [ ] JSON- oder Form-Encoding bewusst auswählen und testen.
- [ ] `accessToken`, `expiresIn` und `tokenType` validieren.
- [ ] Token ausschließlich im Speicher halten.
- [ ] Ablaufzeit monoton berechnen und 60 Sekunden Sicherheitsmarge berücksichtigen.
- [ ] Vor Ablauf automatisch ein neues Token per Client-Credentials-Flow beziehen.
- [ ] Keinen Refresh-Token-Flow implementieren.
- [ ] Connect- und Read-Timeouts setzen.
- [ ] Fehlerantworten redigiert in eigene Exception-Typen überführen.
- [ ] Unit-Tests für Erfolg, ungültige Antwort, `400`, `401`, `500`, `502`, `503` und Timeout ergänzen.

**Abnahme:** Token werden wiederverwendet und rechtzeitig ersetzt; Secrets und Access Tokens erscheinen nicht im Log.

## M4A – Containerisierter Auth-only-QS-Check

**Priorität:** Blocker vor M5  
**Abhängigkeiten:** M2, M4

Dieser Zwischenstand weist die Anmeldung mit dem neu implementierten Code nach, bevor Fahrzeug- oder Telemetrie-Endpunkte entwickelt werden.

- [ ] Einen separaten Einstiegspunkt `python -m polestar_mqtt.auth_check` implementieren.
- [ ] Ausschließlich Konfiguration laden und `POST /token` über den neuen `TokenProvider` ausführen.
- [ ] Keine Fahrzeug-, Battery-, MQTT- oder openWB-Verbindung aufbauen.
- [ ] Bei Erfolg nur eine redigierte Zusammenfassung ausgeben: HTTP-Erfolg, Token-Typ und `expiresIn`; niemals Client Secret oder Access Token.
- [ ] Für Erfolg Exit-Code 0 und für Konfigurations-, Authentifizierungs- oder Transportfehler einen Exit-Code ungleich 0 liefern.
- [ ] Den Check mit den lokalen, ignorierten Credentials containerisiert ausführen:

  ```sh
  docker compose build polestar2mqtt
  docker compose run --rm polestar2mqtt python -m polestar_mqtt.auth_check
  ```

- [ ] Im Testprotokoll nur Zeitpunkt, Ergebnis, Token-Typ und Laufzeit festhalten.

**Abnahme:** Der neu gebaute Container bezieht mit den lokalen Credentials über den neuen Code erfolgreich einen Access Token und beendet sich mit Exit-Code 0, ohne einen fachlichen API-Endpunkt aufzurufen oder vertrauliche Werte auszugeben. Erst danach beginnt M5.

## M5 – Data-Portal-Client für Fahrzeuge und Battery implementieren

**Priorität:** Hoch  
**Abhängigkeiten:** M4A

- [ ] Gemeinsame Header mit Bearer Token, `x-client-id` und `Accept: application/json` erzeugen.
- [ ] `GET /v1/vehicles` implementieren.
- [ ] Konfigurierte VIN gegen die autorisierte Fahrzeugliste prüfen.
- [ ] `GET /v1/vehicles/{vin}/telemetry/battery` implementieren.
- [ ] VIN als Pfadparameter sicher behandeln.
- [ ] `data.batteryChargeLevelPercentage` extrahieren und als numerischen Wert von 0 bis 100 validieren.
- [ ] Optionale bzw. fehlende Telemetriefelder korrekt behandeln.
- [ ] Antwort-VIN gegen die konfigurierte VIN validieren.
- [ ] Quellzeitstempel aus `data.timestamp.seconds` und `nanos` verarbeiten, sofern vorhanden.
- [ ] Bei `401` genau einmal ein neues Token holen und den Request wiederholen.
- [ ] `400`, `403`, `404`, `429`, `500` und `503` fachlich unterscheiden.
- [ ] Exponentielles Backoff mit Jitter für temporäre Fehler vorsehen und `Retry-After` beachten.
- [ ] Unit-Tests für alle Erfolgs-, Daten- und Fehlerfälle ergänzen.

**Abnahme:** Eine autorisierte VIN liefert einen validierten SoC; ungültige oder fehlende Daten werden nicht als erfolgreicher Messwert ausgegeben.

## M6 – MQTT- und openWB-Ausgabe migrieren

**Priorität:** Hoch  
**Abhängigkeiten:** M3, M5

- [ ] Bestehenden kompatiblen SoC-Topic beibehalten:
  - [ ] `<base>/carTelematics/battery/batteryChargeLevelPercentage`
- [ ] SoC retained mit QoS 1 publizieren.
- [ ] Bestehendes LWT unter `<base>/container/connected` beibehalten.
- [ ] `<base>/container/last_update` nur nach erfolgreichem Battery-Abruf aktualisieren.
- [ ] Redigierten Fehlerstatus unter `<base>/container/last_error` bereitstellen.
- [ ] Quellzeitstempel optional unter `<base>/carTelematics/battery/sourceTimestamp` publizieren.
- [ ] Credential-Überwachung retained publizieren:
  - [ ] `<base>/container/credentials/client_secret_expires_at`
  - [ ] `<base>/container/credentials/client_secret_days_remaining`
  - [ ] `<base>/container/credentials/client_secret_status`
- [ ] Change Detection für SoC beibehalten.
- [ ] openWB nur mit vorhandenem, validiertem SoC aktualisieren.
- [ ] Tests mit gemocktem MQTT-Client für Topics, Payload, QoS und Retain ergänzen.

**Abnahme:** Bestehende Node-RED- und openWB-Verbraucher erhalten weiterhin denselben SoC, ohne ihre Topic-Konfiguration ändern zu müssen.

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
