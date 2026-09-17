# Tasks: Migration auf die offizielle Polestar Data Portal API

Diese Taskliste setzt das [MVP-Konzept](MVP-offizielle-Data-Portal-API.md) für Login und SoC-Abruf um. Die Reihenfolge berücksichtigt technische Abhängigkeiten. M8 liefert den funktionalen End-to-End-Nachweis; abgeschlossen ist die Migration nach der anschließenden Bereinigung in M9.

**QS-Ergänzungen vom 17.09.2026:** Dokumentierte Fortschritte und Nachweise bleiben
erhalten; ergänzende Prüfungen werden als neue offene Aufgaben geführt. Für die
Telemetrie gilt die bewusst angepasste Zielsetzung: Topics entstehen dynamisch
aus der API-Antwort. Eine Rückwärtskompatibilität zu Legacy-Telemetrie-Topics wird
nicht zugesichert. Ein optionales Beispiel-Mapping erleichtert Anwendern den
Übergang und wird nicht automatisch aktiviert. Diese Entscheidung ersetzt die
abweichende Kompatibilitätszusage im bisherigen MVP-Konzept; die separat
verwaltete Betriebs- und Statusschnittstelle bleibt erhalten.

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

### M6.1 – Dynamische Topics und Mapping-Vertrag

- [x] Erfolgreiche Data-Portal-JSON-Antworten rekursiv in MQTT-Topics auflösen; Objektpfade bilden dabei automatisch die Topic-Struktur.
- [x] Neue oder bislang unbekannte Telemetriefelder ohne Codeänderung automatisch publizieren.
- [x] Topic-Segmente aus JSON-Schlüsseln deterministisch und MQTT-sicher normalisieren.
- [x] Skalare JSON-Werte retained mit QoS 1 publizieren; Objekte und Arrays rekursiv behandeln.
- [x] Eine optionale lokale CSV-Mapping-Datei für zusätzliche Topics unter `/local-files/mqtt_topic_mapping.csv` einführen und über `local-files` in den Container einbinden; JSON ist als Mapping-Format ausdrücklich ausgeschlossen.
- [x] Das CSV-Mapping ordnet über die Spalten `source_path,target_topic` einen JSON-Quellpfad einer Liste aus einem oder mehreren Ziel-Topics zu; mehrere Ziele werden als mehrere Zeilen mit identischem `source_path` eingetragen.
- [x] Relative Mapping-Ziele unterhalb von `MQTT_BASE_TOPIC` und ausdrücklich absolute Ziel-Topics unterstützen.
- [x] Werte direkt aus dem ursprünglichen API-JSON über `source_path` in Punktnotation lesen und auf den zusätzlichen MQTT-Zielen publizieren; beispielsweise `carTelematics.battery.soc → absolute:openWB/LP1/SoC` bei entsprechend aufgebautem JSON. Keine MQTT-Topics als Quelle verwenden. Die dynamische Ausgabe darf weder ersetzt noch unterdrückt werden; für die tatsächliche Battery-Antwort lautet der SoC-Quellpfad `data.batteryChargeLevelPercentage`.
- [x] Fehlende Mapping-Datei als gültige Standardkonfiguration behandeln; ungültige Einträge mit verständlichen, redigierten Meldungen ablehnen.
- [x] Den dynamischen Wurzelpfad und die Behandlung von `data`, `meta` sowie identifizierenden Feldern wie VIN ausdrücklich dokumentieren; daraus die Veröffentlichung unbekannter Telemetriefelder ohne feste Feldliste ableiten.
- [x] Die festgelegte Punktnotation für JSON-Quellpfade um eindeutige Regeln für Escaping und Array-Indizes vervollständigen und mit CSV-Beispielen dokumentieren; absolute MQTT-Ziele sind bereits durch `absolute:` gekennzeichnet.
- [x] Alle Ziele vor dem Publizieren auf MQTT-Gültigkeit und Kollisionen prüfen; unterschiedliche Quellen für dasselbe Ziel sowie Kollisionen mit dynamischen Topics ablehnen, identische Zuordnungen deduplizieren.
- [x] Eine versionierte, ausschließlich optional zu aktivierende CSV-Mapping-Beispieldatei für die wichtigsten tatsächlich verfügbaren Battery-Werte bereitstellen. Gemäß Nutzeranpassung relative Testziele unter `mappingtest/` und eine zusätzliche SoC-Ausgabe auf `absolute:polestar2-test-DataPortalAPI_absolute/SoC` zeigen; keine Legacy-Topic-Vorgabe.
- [x] In der Beispiel-Dokumentation erklären, dass fehlende Legacy-Felder nicht nachgebildet werden und Anwender die Zuordnungen für ihre Verbraucher prüfen müssen. Ohne lokale Mapping-Datei ausschließlich dynamische Telemetrie-Topics ausgeben.
- [x] Eine Entscheidungstabelle für Transportfehler, ungültige Antworten, gültige Teilantworten, fehlende Felder, explizites `null` und alte oder fehlende Quellzeitstempel festlegen. Je Fall Veröffentlichung, Beibehalten oder Löschen retained gespeicherter Werte, Statusausgabe und openWB-Verhalten definieren; HTTP 200 allein ist kein gültiger Messwert. Siehe [Datenzustände und Ausgabeentscheidungen](../doc/data-portal-data-states.md).
- [x] Payload-Regeln für Zahlen, Boolean, leere Strings und `null` dokumentieren und gegen das MVP-Konzept abstimmen; Nutzwerte klar von Zero-Length-Lösch-Payloads unterscheiden. Siehe [Payload-Vertrag](../doc/data-portal-data-states.md#payload-vertrag); die missverständliche `null`-Löschregel im MVP-Konzept ist korrigiert.

**QS-Nachweis Zielauflösung vom 17.09.2026:** Auf Basis von Commit `f29fbd9`
mit lokalen, nicht committeten Änderungen an Konfiguration, Publisher, Tests
und Dokumentation wurde `resolve_topic_mapping()` ergänzt. Relative Ziele werden
unterhalb der Basis aufgelöst; `absolute:` kennzeichnet ein Ziel ohne Basis-Präfix.
Die Regeln und Beispiele stehen in [`doc/README.md`](../doc/README.md).
`./run_tests.sh` lief mit erfolgreichem Ruff-Check, 160 bestandenen Tests und
Exit-Code 0 durch. Geprüft wurden gemischte relative/absolute CSV-Ziele,
abschließende Basis-Slashes, explizite führende Topic-Slashes, äquivalente Ziele
und leere beziehungsweise mehrdeutige Angaben. Der vom Testskript zusätzlich
gestartete Legacy-E2E-Lauf beendete einen Zyklus; er prüft nicht die neue
Mapping-Ausgabe und gab vertrauliche Debug-Daten aus, die hier nicht übernommen
werden. Die eigentliche Mapping-Veröffentlichung bleibt der nächste offene Schritt.

**Präzisierung JSON-Quelle vom 17.09.2026:** Der CSV-Parser akzeptiert jetzt
JSON-Pfade in Punktnotation. Die Zielauflösung erhält diese Quellpfade unverändert;
sie löst ausschließlich die MQTT-Zielnamen auf. Das Beispiel
`carTelematics.battery.soc,absolute:openWB/LP1/SoC` ist durch einen Regressionstest
abgedeckt. Auf derselben Commit-Basis mit lokalen Änderungen an Parser, Tests und
Dokumentation lief `./run_tests.sh` mit erfolgreichem Ruff-Check, 166 bestandenen
Tests und Exit-Code 0 durch. Der zusätzliche Legacy-E2E-Lauf beendete einen Zyklus;
die direkte JSON-Wertauswertung und zusätzliche Veröffentlichung bleiben offen.

**QS-Nachweis zusätzliche JSON-Ausgabe vom 17.09.2026:** Auf Basis von Commit
`f29fbd9` mit lokalen Änderungen an Publisher, Tests und Dokumentation publiziert
`publish_json_topics()` nun zusätzlich die über JSON-Punktpfade zugeordneten
skalaren Werte. Der Test für `carTelematics.battery.soc` bestätigt die Ausgabe
auf `openWB/LP1/SoC` und einem relativen Ziel bei unveränderter dynamischer Ausgabe.
Fehlende oder nicht skalare Quellen unterdrücken keine dynamischen Topics;
Zielkonflikte werden vor dem ersten Publish abgelehnt. `./run_tests.sh` bestand
mit Ruff, 179 erfolgreichen Tests und Exit-Code 0. Der zusätzliche Legacy-E2E-Lauf
beendete einen Zyklus; er ist kein Live-Nachweis der neuen Mapping-Ausgabe.
Dateiladen, vollständige Pfad-Syntax und Integration in die Programmsteuerung
bleiben den weiteren Aufgaben vorbehalten.

**QS-Nachweis optionales Dateiladen vom 17.09.2026:** Auf Basis von Commit
`f29fbd9` mit lokalen Änderungen an Publisher, Tests und Dokumentation wurde
`load_topic_mapping()` ergänzt. Fehlende Dateien ergeben ein leeres Mapping;
vorhandene Dateien werden als UTF-8 (optional mit BOM) eingelesen, geprüft und
aufgelöst. Fehlerhafte Kopfzeilen, zusätzliche oder fehlende Spalten, ungültige
CSV-Syntax, ungültige Quell-/Zielangaben gemäß bisherigem Vertrag, Encoding- und
Lesefehler werden ohne Ausgabe von Pfad oder Dateiinhalt abgelehnt. Fehlermeldungen
für CSV-Zeilen nennen die physische Zeilennummer. Eine reine Kopfzeile ist gültig;
eine vorhandene leere Datei gilt als Konfigurationsfehler. `./run_tests.sh` bestand
nach einer selektiven Ruff-Zeilenlängenkorrektur mit Ruff, 194 erfolgreichen Tests
und Exit-Code 0. Der zusätzliche Legacy-E2E-Lauf beendete einen Zyklus; er prüft
nicht das neue Dateiladen. Vollständige MQTT-Zielvalidierung, erweiterte Pfad-Syntax
und Einbindung in die Programmsteuerung bleiben separate Aufgaben.

**Dokumentationsnachweis Topic-Baum vom 17.09.2026:** In
[`doc/README.md`](../doc/README.md#data-portal-ausgabe-dynamischer-topic-baum)
ist `<MQTT_BASE_TOPIC>/telemetry/battery` als Battery-Wurzel festgelegt. Die
vollständige validierte Antwort behält `data` und `meta`; vorhandene VIN- und
sonstige Identifikationsfelder werden als MQTT-Nutzwerte mitpubliziert, ohne
eine VIN in der Wurzel einzuführen. Neue skalare Felder werden ohne Feldliste
rekursiv ergänzt. JSON-Quellpfade des Mappings bleiben unabhängig von der
MQTT-Wurzel. Die Dokumentation wurde gegen Publisher, vorhandene Unit-Tests
und synthetische Battery-Fixture abgeglichen; `git diff --check` war erfolgreich.
Basis: `f29fbd9` mit bestehenden lokalen Änderungen. Dieser Schritt ändert nur
Dokumentation; keine erneuten Anwendungs- oder Live-Tests. Die Einbindung der
festgelegten Wurzel in die Programmsteuerung bleibt offen.

**QS-Nachweis Pfad-Syntax vom 17.09.2026:** Punktpfade unterstützen jetzt
maskierte Punkte (`\.`), Backslashes (`\\`), Slashes (`\/`) und leere Schlüssel
(`\e`). Numerische Segmente adressieren Arrays ab Index 0 und bleiben bei Objekten
wörtliche Schlüssel. Parser und Publisher verwenden dieselbe Pfad-Auswertung;
fehlerhafte Escapes werden vor dem Publizieren abgelehnt. CSV-Beispiele und
Grenzen stehen in `doc/README.md`. Auf Basis `f29fbd9` mit lokalen Änderungen an
Publisher, Tests und Dokumentation bestand `./run_tests.sh` mit Ruff, 223 Tests
und Exit-Code 0. Dieser Schritt betrifft ausschließlich die Mapping-Pfadsyntax;
es wurde kein Container-Test durchgeführt.

**QS-Nachweis Zielvalidierung vom 17.09.2026:** Alle dynamischen und konfigurierten
Mapping-Ziele werden vor dem ersten Publish auf nicht leere, gültige UTF-8-Namen,
maximal 65.535 UTF-8-Bytes und Ausschluss von NUL und Wildcards geprüft. Konflikte
zwischen unterschiedlichen Quellen oder mit dynamischen Topics werden auch bei
fehlenden Quellen und gleichen Werten abgelehnt; identische Zuordnungen werden
dedupliziert. Die vereinfachte Prüfung im Einmallauf nutzt nun denselben Validator.
Auf Basis `f29fbd9` mit lokalen Änderungen an Publisher, Einmallauf, Tests und
Dokumentation bestand `./run_tests.sh` mit Ruff, 247 Tests und Exit-Code 0.
UTF-8-Bytegrenzen, fehlerhafte dynamische Namen, Kollisionen und ausbleibende
Publishes bei Fehlern sind automatisiert abgedeckt. `git diff --check` erfolgreich.
Kein Container-Test; der Container-Namespace-Schutz bleibt separat offen.

**QS-Nachweis Beispiel-Mapping vom 17.09.2026:** Die für die Versionierung
vorgesehene Datei `local-files/mqtt_topic_mapping.csv_sample` enthält vier
JSON-Pfad-Zuordnungen für SoC, Ladestatus, Restladezeit (Minuten) und Restreichweite
(Kilometer). Die Felder sind aus der Battery-Ausgabe bekannt und entsprechen den
bisherigen gleichnamigen Battery-Feldern. Alle Ziele liegen relativ zur
konfigurierten MQTT-Basis unter `carTelematics/battery`; die Vorlage wird nicht
automatisch aktiviert. Die aktive lokale CSV ist in `.gitignore` aufgenommen.
Mit dem vorhandenen Loader und Publisher wurden alle vier Zuordnungen gegen die
synthetische Battery-Fixture mit synthetisch ergänzter Restladezeit geprüft:
zusätzliche und dynamische Payloads stimmen überein, QoS 1 und Retain bleiben
erhalten. Prüfung ohne Netzwerkzugriff mit gemocktem MQTT-Client; keine aktive
Mapping-Datei angelegt. `git diff --check` erfolgreich. Keine Python-Codeänderung,
daher kein erneuter vollständiger Test- oder Live-Lauf.

### M6.2 – Bestätigte Veröffentlichung und dauerhaftes Topic-Inventar

- [ ] Die zuletzt erfolgreich publizierte Menge der verwalteten dynamischen und Mapping-Topics in einer lokalen Zustandsdatei außerhalb des Containers persistieren.
- [ ] Die Zustandsdatei über `local-files` dauerhaft in den Container einbinden und atomar aktualisieren, damit Container-Neustarts die Topic-Historie nicht verlieren.
- [ ] Nach einer fachlich validierten API-Antwort die zuvor persistierten Topics mit der gemäß Entscheidungstabelle aktuell erzeugten Topic-Menge vergleichen; Transportfehler und abgelehnte Antworten dürfen keine Inventarbereinigung auslösen.
- [ ] Nicht mehr erzeugte verwaltete Topics mit einem leeren retained Publish (Zero-Length-Payload) und QoS 1 aus dem Broker löschen.
- [ ] Vor dem ersten Publish einen ausstehenden Vorgang mit bisheriger und beabsichtigter Topic-Menge dauerhaft speichern. Die neue Topic-Menge erst als abgeschlossen übernehmen, nachdem alle aktuellen Publishes und erforderlichen Lösch-Publishes erfolgreich bestätigt wurden; Wiederaufnahme nach Absturz idempotent gestalten.
- [ ] Bestätigungen und deren Timeouts ausdrücklich auswerten; ein Aufruf von `publish()` allein gilt nicht als erfolgreiche Zustellung.
- [ ] Das Inventar versionieren und an Broker sowie Publisher-Instanz binden. Verhalten bei Wechsel von Broker oder `MQTT_BASE_TOPIC`, fehlender oder beschädigter Zustandsdatei und parallelen Instanzen festlegen; bei unklarer Zuständigkeit keine Topics löschen.
- [ ] Exklusive Zuständigkeit für dynamische und zusätzliche Mapping-Ziele dokumentieren, insbesondere für absolute Ziele außerhalb von `MQTT_BASE_TOPIC`; eine Inventaraufnahme allein begründet kein Eigentum an fremden Topics.
- [ ] Ausschließlich vom Telemetrie-Publisher verwaltete dynamische und Mapping-Topics löschen; Containerstatus-, Credential- und fremde Topics niemals aus dem Inventar ableiten oder entfernen.
- [ ] `<base>/container` einschließlich aller Unterpfade als stabile, separat verwaltete Betriebs- und Statusschnittstelle schützen (MQTT-Filter `<base>/container/#`); diesen Bereich weder dynamisch aus API-JSON erzeugen noch in das Telemetrie-Topic-Inventar aufnehmen.
- [ ] Relative und absolute Mapping-Ziele im gesamten geschützten Container-Namespace ablehnen.
- [ ] Den Umgang mit alten retained GraphQL-Topics dokumentieren: Sie gehören nicht automatisch zum neuen Inventar. Eine gezielte manuelle Bereinigung erläutern; keine pauschale Löschung des bisherigen Topic-Baums vorsehen.

### M6.3 – Betriebsstatus, Change Detection und openWB

- [ ] Bestehendes LWT unter `<base>/container/connected` beibehalten.
- [ ] `<base>/container/last_update` als Zeitpunkt des letzten fachlich erfolgreichen Battery-Abrufs definieren und nur dann aktualisieren. Abrufzeit, Quellzeit und MQTT-Zustellstatus unterscheiden; ein alter Quellzeitstempel darf nicht als neue Messung dargestellt werden.
- [ ] Redigierten Fehlerstatus unter `<base>/container/last_error` bereitstellen.
- [ ] Bestehendes `<base>/container/last_exception` beibehalten und ausschließlich redigierte technische Fehlerinformationen publizieren.
- [ ] Den Quellzeitstempel über die dynamischen Topics zugänglich machen; eine gegebenenfalls zusätzlich aufbereitete Darstellung samt Format und Mapping-Quellpfad ausdrücklich definieren, ohne einen festen Legacy-Telemetrie-Topic vorauszusetzen.
- [ ] Credential-Überwachung retained publizieren:
  - [ ] `<base>/container/credentials/client_secret_expires_at`
  - [ ] `<base>/container/credentials/client_secret_days_remaining`
  - [ ] `<base>/container/credentials/client_secret_status`
- [ ] Change Detection für SoC beibehalten.
- [ ] Nach MQTT-Reconnect aktuelle Telemetrie- und Betriebswerte erneut publizieren, auch bei unverändertem SoC; insbesondere einen Broker-Neustart ohne retained Bestand berücksichtigen.
- [ ] Credential-Warnungen ab 14 verbleibenden Tagen auch im Fehlerstatus berücksichtigen. Priorität und Rücksetzen von API-, MQTT-, openWB- und Credential-Fehlern festlegen; ein erfolgreicher Battery-Abruf darf eine weiterhin aktive Credential-Warnung nicht löschen.
- [ ] openWB nur mit vorhandenem, validiertem SoC aktualisieren.
- [ ] Die optionale openWB-Verbindung und ihre Fehlerbehandlung von der Hauptausgabe trennen; ein openWB-Ausfall darf die Telemetrie-Veröffentlichung am Hauptbroker nicht blockieren. Mapping-Ziele bezeichnen Topics, keine zusätzlichen Brokerverbindungen.

### M6.4 – QS und Abnahme

- [ ] Tests mit gemocktem MQTT-Client für rekursive dynamische Topics, neue JSON-Felder, Mapping auf mehrere Ziele, fehlende und ungültige Mapping-Dateien, persistiertes Topic-Inventar, verwaiste retained Topics, Payload, QoS und Retain ergänzen.
- [ ] Regressionstests für Zielkollisionen, geschützte Unterpfade, Teilantworten, `null`, veraltete Messwerte, Zustellfehler und beschädigte oder nicht zuordenbare Inventare ergänzen.
- [ ] Abstürze vor und nach einzelnen Publishes, Löschungen und Inventarabschlüssen testen; nach Neustart dürfen auch bereits zugestellte neue Topics nicht aus der Bereinigung verloren gehen.
- [ ] Einen getrennten Integrationstest mit lokalem Testbroker für retained Werte, bestätigte Löschungen, Reconnect und Wiederveröffentlichung durchführen; Unit-Tests weiterhin ohne Netzwerkzugriff ausführen.

**Abnahme:** Die MQTT-Ausgabe bildet die gelieferte JSON-Struktur ohne fest codierte
Telemetriefeldliste dynamisch ab. Ohne Mapping-Datei entstehen keine zusätzlichen
Legacy-Telemetrie-Topics. Das optionale Beispiel-Mapping erleichtert die gezielte
Umstellung vorhandener Verbraucher, ohne Rückwärtskompatibilität zu garantieren.
Lokale Mappings können denselben Quellwert in
mehrere zusätzliche Topics schreiben und damit bestehende Node-RED-, openWB-
oder andere Zielsysteme versorgen, ohne die dynamischen Standard-Topics zu
verändern. Nach Container-Neustarts werden nicht mehr erzeugte, zuvor vom
Telemetrie-Publisher verwaltete retained Topics zuverlässig aus dem Broker
entfernt, auch nach einem Absturz während einer nur teilweise bestätigten
Veröffentlichung. Fremde und nicht eindeutig zuordenbare Topics bleiben geschützt.
Die bestehende `<base>/container/#`-Schnittstelle bleibt stabil und
wird gezielt um neue Betriebsfunktionen wie den Credential-Status ergänzt.

## M6A – Lokaler Data-Portal-Einmallauf mit MQTT-Ausgabe

**Priorität:** Vorgezogener QS-Zwischenschritt auf Nutzerwunsch

**Abhängigkeiten:** M5 und bereits umgesetzte Publisher-/Mapping-Bausteine aus M6

- [x] Den bisherigen `soc-check` zu `./run_local.sh runonce-DataPortalAPI` mit Einstiegspunkt `python -m polestar_mqtt.runonce` refaktorieren; bisherige SoC-Check-Aufrufe als dokumentierte Aliase mit MQTT-Ausgabe erhalten.
- [x] Einmal authentifizieren, VIN-Berechtigung prüfen und die aktuelle Battery-Antwort einschließlich SoC und optionalem Quellzeitstempel validieren.
- [x] Die Antwort unter `<MQTT_BASE_TOPIC>/telemetry/battery` dynamisch und zusätzlich über ein optionales JSON-Pfad-Mapping publizieren; lokal die Mapping-Datei im Repository-Verzeichnis `local-files` als Default verwenden.
- [x] MQTT-Zugangsdaten aus der vorhandenen Konfiguration verwenden; Verbindungsbestätigung und QoS-1-Publish-Bestätigungen mit begrenzter Wartezeit prüfen, danach MQTT-Verbindung und Netzwerkschleife beenden.
- [x] Nur eine Zusammenfassung ohne Credentials, Token, VIN oder Messwerte ausgeben; Fehler mit Exit-Code ungleich 0 melden.
- [x] Automatisierte Tests für Erfolg, zusätzliche Mapping-Ausgabe, ungültigen SoC, Konfigurationsfehler, Broker-Ablehnung, Verbindungs-/Publish-Fehler und ausbleibende Bestätigungen ausführen.
- [x] Den Einmallauf lokal mit echten Credentials und konfiguriertem MQTT-Testtopic ausführen.

**Abnahme:** Ein lokaler Aufruf liest die aktuelle Data-Portal-Antwort und endet
mit Exit-Code 0 erst nach Bestätigung sämtlicher MQTT-Publishes. Dieser
Zwischenschritt ersetzt weder die vollständige M6-Abnahme noch M7/M8.
Container-Test ausdrücklich auf Nutzerwunsch zurückgestellt. Dauerbetrieb,
Status-/Credential-Topics, Topic-Inventar und separate openWB-Verbindung bleiben
in ihren bisherigen Aufgaben; absolute Mapping-Ziele publizieren am Hauptbroker.

**Lokaler QS-Nachweis vom 17.09.2026:** Basis `f29fbd9` mit lokalen Änderungen
an Einmallauf, SoC-Check-Alias, Startskripten, Tests und Dokumentation.
`./run_tests.sh`: Ruff erfolgreich, 203 Tests bestanden, Exit-Code 0; der darin
enthaltene zusätzliche Legacy-E2E-Lauf ist kein Data-Portal-Nachweis.
`./run_local.sh runonce-DataPortalAPI`: neuer Data-Portal-Lauf erfolgreich,
17 MQTT-Publishes unter `polestar2-test/telemetry/battery` bestätigt, Exit-Code 0.
Das Testtopic wurde aus `.env_local` geladen; der lokale Start liest keine
Compose-Datei. Ohne lokale Mapping-Datei wurden nur dynamische Topics publiziert.
Ein erster sandboxbeschränkter Versuch scheiterte am Netzwerkzugriff; der
anschließend mit freigegebenem Netzwerkzugriff wiederholte Lauf war erfolgreich.
Es wurde kein Container gebaut oder gestartet.

## M7 – Polling, Fehlerbehandlung und Shutdown überarbeiten

**Priorität:** Hoch  
**Abhängigkeiten:** M5, M6

- [ ] Startreihenfolge festlegen: Konfiguration, MQTT, Credential-Status, Token, VIN-Prüfung, Polling.
- [ ] Das bisherige `wait_and_die()` entfernen.
- [ ] Temporäre API-Fehler ohne Prozessende behandeln.
- [ ] Ungültige lokale Konfiguration wie in M2 beim Start ablehnen. Berechtigungs- und Credential-Fehler zur Laufzeit klar kennzeichnen und mit langsamem Retry behandeln, damit MQTT-Status beobachtbar bleibt.
- [ ] Zuständigkeit und Gesamtbudget für Retries zwischen HTTP-Client, TokenProvider und Polling festlegen; Anzahl der Versuche, Backoff-Obergrenzen und Verhalten nach Erschöpfung dokumentieren, damit verschachtelte Retries keine Request-Flut erzeugen.
- [ ] Ergänzende M5-QS: `502` wie im MVP-Konzept als temporären Fehler behandeln und durch Regressionstest absichern.
- [ ] Ergänzende M5-QS: Höchstens einen durch `401` ausgelösten Token-Neubezug pro fachlichem Request auch über gemischte Folgen wie `401 → 503 → 401` sicherstellen; einen bereits verbrauchten Auth-Retry nicht durch Transport- oder Serverfehler zurücksetzen.
- [ ] Token-Endpunkt-Ausfälle und die Erholung nach ausgeschöpften Retries ausdrücklich testen.
- [ ] Eine enge Docker-Restart- oder Token-Request-Schleife verhindern.
- [ ] SIGTERM-Verarbeitung und MQTT-Disconnect beibehalten bzw. testen.
- [ ] Polling-, Backoff- und `Retry-After`-Wartezeiten unterbrechbar gestalten; SIGTERM während langer Wartezeiten und laufender Requests innerhalb einer dokumentierten Shutdown-Frist testen.
- [ ] Systemzeitänderungen dürfen die Access-Token-Frist nicht verfälschen; monotone Zeit verwenden.
- [ ] Integrationstests für mehrere Polling-Zyklen, Token-Erneuerung und Fehlererholung ergänzen.

**Abnahme:** Der Dienst läuft nach temporären HTTP- und MQTT-Problemen weiter und beendet sich bei SIGTERM sauber.

## M8 – Container, Deployment und Dokumentation migrieren

**Priorität:** Hoch  
**Abhängigkeiten:** M2–M7

- [ ] `docker-compose_example.yml` auf die neuen Variablen und sichere Platzhalter umstellen.
- [ ] `POLESTAR_EMAIL` und `POLESTAR_PASSWORD` aus der Deployment-Vorlage entfernen.
- [ ] Den ausführbaren Einstiegspunkt der neuen Programmsteuerung fertigstellen und Docker-`CMD`, den normalen lokalen Start sowie `runonce` darauf umstellen; keine Legacy-Credentials mehr in diesen Startwegen voraussetzen.
- [ ] `README.md` mit Credential-Erstellung, Secret-Ablaufdatum, Migration und MQTT-Vertrag aktualisieren.
- [ ] Das MVP-Konzept mit der hier festgelegten dynamischen Topic-Ausgabe und dem optionalen Beispiel-Mapping synchronisieren; bereits geklärte API-Fragen auf die M0-Nachweise verweisen lassen.
- [ ] Schreibrechte des Containerbenutzers auf dem dauerhaft eingebundenen Zustandsverzeichnis sowie Verhalten bei Schreibfehlern prüfen und dokumentieren.
- [ ] `Synology-howto.md` aktualisieren.
- [ ] Lokale, ignorierte `docker-compose.yml` für den E2E-Test anpassen.
- [ ] Docker-Image lokal bauen und automatisierte Tests darin ausführen.
- [ ] Multi-Arch-Build im Workflow `.github/workflows/docker-image.yml` verifizieren.
- [ ] End-to-End-Test mit echten Credentials, MQTT und optional openWB zuerst über den normalen lokalen Start und danach über den regulären Container-Start durchführen; keinen Auth-/SoC-Sondereinstieg als Ersatz verwenden. `runonce` separat prüfen.
- [ ] Im E2E-Test sowohl Betrieb ohne Mapping als auch die ausdrücklich aktivierte Beispiel-Zuordnung prüfen; dynamische Topics müssen in beiden Fällen erhalten bleiben.
- [ ] Vor einem Produktionsrelease die Endpunkt-Klassifizierung aus M0 erneut prüfen und dokumentieren. Ein erfolgreicher Sandbox-Test allein ist kein Nachweis einer Produktionsfreigabe; einen weiter bestehenden Sandbox-Vorbehalt in den Release-Hinweisen ausweisen.
- [ ] In Logs und MQTT prüfen, dass weder Client Secret noch Access Token vorkommen.
- [ ] Neue QS-Nachweise mit Zeitpunkt, Szenario, Ergebnis und Commit beziehungsweise Image-Digest versehen; lokale Abweichungen vom Commit benennen, vertrauliche Daten weiterhin auslassen.

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
- [ ] Den E2E-Test nach Entfernung des Legacy-Codes mit dem finalen Image über dessen regulären Startweg wiederholen und den getesteten Image-Digest dokumentieren.
- [ ] Release Notes mit Breaking Changes und Migrationsanleitung erstellen.

**Abnahme:** Zur Laufzeit existiert keine Abhängigkeit mehr von der inoffiziellen API; Tests, Image-Build und E2E-Test sind erfolgreich.

## Nicht Teil dieses MVP

- weitere Telemetriedomänen wie Odometer, Location, Exterior oder Health
- Charging-Schreiboperationen
- Delegation über `x-delegated-account-id`
- automatische Erstellung oder Rotation des Client Secrets
- persistente Speicherung bereits ausgegebener Ablaufwarnungen
- automatische Auswahl einer VIN bei mehreren Fahrzeugen
- garantierte Rückwärtskompatibilität zu Legacy-Telemetrie-Topics oder automatische Aktivierung des Beispiel-Mappings
