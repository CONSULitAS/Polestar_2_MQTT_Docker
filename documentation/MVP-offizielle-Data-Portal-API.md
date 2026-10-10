# MVP-Konzept: offizielle Polestar Data Portal API

## Ziel und Abgrenzung

Der erste Rewrite-Schritt ersetzt die bisherige inoffizielle Polestar-ID-/GraphQL-Anbindung durch die offizielle M2M-API. Der MVP soll:

1. sich per OAuth2 Client Credentials authentifizieren,
2. die Berechtigung für die konfigurierte VIN prüfen,
3. die lesenden Fahrzeugendpunkte aus einer validierten OpenAPI-Spezifikation ermitteln,
4. alle katalogisierten Telemetrie- und Charging-Endpunkte zyklisch generisch abrufen,
5. deren JSON-Antworten dynamisch über MQTT veröffentlichen und den validierten Batterie-SoC optional an openWB weiterreichen.

Nicht Teil des MVP sind Schreiboperationen, eine automatische Migration aller
bisherigen MQTT-Felder, Third-Party-Delegation sowie die ungeprüfte automatische
Übernahme beliebiger OpenAPI-Änderungen. Kompatible neue lesende Fahrzeugendpunkte
sollen dagegen ohne neue endpunktspezifische Programmlogik übernommen werden.

## Ausgangslage und API-Vertrag

Die bisherige Implementierung simuliert einen Benutzer-Login mit E-Mail, Passwort und PKCE und ruft anschließend die nicht offizielle GraphQL-API `mystar-v2` auf. Die offizielle API arbeitet anders:

- Basis-URL: `https://pc-api.polestar.com/eu-north-1/data-portal/m2m`
- Authentifizierung: `POST /token` mit `clientId`, `clientSecret` und optionalem `scope`
- Token-Antwort: `accessToken`, `expiresIn`, `tokenType`; es gibt laut Spezifikation keinen Refresh-Token
- Fahrzeugliste: `GET /v1/vehicles`
- Fachliche Fahrzeugdaten: dokumentierte `GET`-Operationen unter `/v1/vehicles/{vin}/telemetry/` und `/v1/vehicles/{vin}/charging/`
- Pflicht-Header an den fachlichen Endpunkten: `Authorization: Bearer ...` und `x-client-id: <Account-ID>`
- Die erforderlichen Scopes stehen je Operation in `x-required-scopes`; der Token-Endpunkt akzeptiert mehrere Scopes als leerzeichenseparierten String.
- Die mitgelieferte OpenAPI-3.1-Datei ist Quelle für Endpoint-Katalog und Scopes, nicht für eine ungeprüfte Änderung der konfigurierten Basis-URL.
- Der gesuchte Wert steht in `data.batteryChargeLevelPercentage`. Alle Telemetriefelder außer `vin` können fehlen.
- Rate Limit: maximal 10.000 Aufrufe pro Client und Tag.

Wichtig ist die begriffliche Trennung zweier IDs: `clientId` ist Teil der OAuth-Credentials; `x-client-id` ist die im Developer Portal gebundene eigene User-/Account-ID. Im Code und in der Konfiguration müssen sie deshalb unterschiedlich benannt werden.

## Zielarchitektur

Die bisherige monolithische Datei sollte beim Rewrite in kleine Verantwortungsbereiche zerlegt werden:

```text
Konfiguration
     |
     v
OpenAPI-Katalog ----> validierte GET-Pfade und Scopes
     |
     v
TokenProvider ------> POST /token mit aggregierten Scopes
     |
     v
PolestarDataPortalClient ----> GET /v1/vehicles
     |                         GET-Schleife über alle katalogisierten Fahrzeugendpunkte
     v
Dynamischer JSON-Publisher ----> MQTT
     |
     `------------------------> SoC-Fachableitung und openWB (optional)
```

Empfohlene Module:

- `config.py`: Umgebungsvariablen lesen und beim Start vollständig validieren
- `openapi_catalog.py`: lokale beziehungsweise gebündelte Spezifikation validieren und sichere GET-Operationen samt Scopes katalogisieren
- `polestar_api.py`: Token-Lebenszyklus, HTTP-Aufrufe, Timeouts und Fehlerabbildung
- `publisher.py`: MQTT- und openWB-Ausgabe
- `main.py`: Start, Fahrzeugprüfung und Polling-Schleife

Alternativ können diese Grenzen im MVP zunächst als Klassen/Funktionen in einer Datei umgesetzt werden. Entscheidend sind getrennte Schnittstellen, damit HTTP- und MQTT-Verhalten unabhängig getestet werden können.

## Konfiguration

Neue Variablen:

| Variable | Pflicht | Zweck |
| --- | --- | --- |
| `POLESTAR_CLIENT_ID` | ja | OAuth Client ID aus den API-Credentials |
| `POLESTAR_CLIENT_SECRET` | ja | OAuth Client Secret |
| `POLESTAR_CLIENT_SECRET_EXPIRES_AT` | ja | Ablaufdatum des Client Secrets im Portalformat `YYYY-MM-DD` |
| `POLESTAR_ACCOUNT_ID` | ja | Wert für den Header `x-client-id` |
| `POLESTAR_VIN` | ja | abzurufendes Fahrzeug |
| `POLESTAR_API_BASE_URL` | nein | überschreibbare Basis-URL, standardmäßig die dokumentierte M2M-URL |
| `POLESTAR_OPENAPI_FILE` | nein | optionale lokale OpenAPI-Datei; standardmäßig `/local-files/Polestar_DataPortalAPI.json`, mit gebündeltem Fallback unter `api/`; sie wird einmal beim Containerstart geladen |
| `POLESTAR_CYCLE` | nein | Polling-Intervall, zunächst weiterhin 270 Sekunden |
| `POLESTAR_DELEGATED_ACCOUNT_ID` | nein/später | optionaler Header für Third-Party-Credentials; nicht MVP |

`POLESTAR_EMAIL` und `POLESTAR_PASSWORD` entfallen. Secrets dürfen weder im Log noch in eingecheckten Compose-Dateien stehen. Für reale Installationen sind Docker Secrets oder eine nicht versionierte `.env` sinnvoll.

Für die Container-Konfiguration gelten zwei getrennte Rollen:

- `docker-compose.yml` ist durch `.gitignore` ausgeschlossen und darf lokale Credentials für den End-to-End-Test enthalten. Sie ist keine Projekt- oder Deployment-Vorlage.
- `docker-compose_example.yml` ist die versionierte Vorlage für Anwender und Deployment. Nur diese Datei wird im Rahmen des Rewrites mit Platzhaltern und den neuen Variablen dokumentiert.

Der versionierte Workflow `.github/workflows/docker-image.yml` baut und veröffentlicht das Image; er enthält keine lokale Laufzeitkonfiguration für den E2E-Test.

### Ablaufdatum des Client Secrets

Das im Developer Portal ausgestellte Client Secret besitzt unabhängig vom Access Token eine begrenzte Lebensdauer (aktuell offenbar 90 Tage). Da die API das Ablaufdatum nicht mit der Token-Antwort liefert, muss es zusammen mit dem Secret konfiguriert werden. `POLESTAR_CLIENT_SECRET_EXPIRES_AT` gehört deshalb zur Credential-Konfiguration und ist für den MVP verpflichtend.

Das von Polestar bereitgestellte Format ist `YYYY-MM-DD`. Beim Einlesen ergänzt die Anwendung `00:00:00` und die über `TZ` konfigurierte Zeitzone. Danach kann der timezone-aware Zeitpunkt für interne Berechnungen eindeutig nach UTC umgerechnet werden.

Beim Start und danach mindestens einmal pro Tag wird die verbleibende Laufzeit geprüft. Empfohlene Warnschwellen sind 30, 14, 7, 3 und 1 Tag sowie 0 Tage. Eine Warnung wird je Schwelle nur einmal ausgegeben, damit der Polling-Zyklus nicht alle 270 Sekunden dieselbe Meldung erzeugt. Ein Container-Neustart darf die aktuelle Warnung einmal erneut ausgeben; eine persistente Warnhistorie ist für den MVP nicht erforderlich. Die Warnung ist ab 14 Tagen vorher ebenfalls auf einen Error-MQTT-Topic auszugeben.

Ausgabewege:

- strukturierte Warnung im Container-Log ohne Ausgabe des Secrets,
- retained MQTT-Topic `<base>/container/credentials/client_secret_expires_at`,
- retained MQTT-Topic `<base>/container/credentials/client_secret_days_remaining`,
- retained MQTT-Topic `<base>/container/credentials/client_secret_status` mit `ok`, `warning`, `critical` oder `expired`.

Statusgrenzen: `ok` bei mehr als 30 Tagen, `warning` bei 30 bis 8 Tagen, `critical` bei 7 bis 1 Tag und `expired` ab dem Ablaufzeitpunkt. Der hinterlegte Ablaufzeitpunkt ist keine geheime Information; Client ID und Client Secret werden weiterhin niemals publiziert.

Ist das Secret bereits abgelaufen, wird der Zustand deutlich publiziert und jeder fehlgeschlagene Token-Abruf als nicht automatisch behebbarer Credential-Fehler behandelt. Der Prozess darf mit langsamem Retry weiterlaufen, damit Status und LWT beobachtbar bleiben, darf aber keine enge Restart- oder Login-Schleife erzeugen. Eine Secret-Erneuerung erfolgt außerhalb der Anwendung; anschließend werden Secret und Ablaufzeitpunkt gemeinsam in der Deployment-Konfiguration ersetzt und der Container neu gestartet.

## Ablauf

### 1. Start und Authentifizierung

1. Konfiguration validieren; bei fehlenden Pflichtwerten mit einer eindeutigen Meldung abbrechen.
2. Lokale OpenAPI-Datei verwenden, sofern vorhanden, andernfalls den gebündelten Fallback laden. Die Datei wird einmal beim Containerstart validiert und katalogisiert; eine Änderung wird erst nach einem Container-Neustart wirksam. Nur validierte GET-Operationen innerhalb der erlaubten Fahrzeugpfade katalogisieren.
3. Scopes aller katalogisierten Operationen deduplizieren und deterministisch als leerzeichenseparierten String bilden.
4. `POST /token` als JSON oder Form-Body senden:

   ```json
   {
     "clientId": "...",
     "clientSecret": "...",
     "scope": "pdp-charging/targetSoc pdp-telemetry/battery ..."
   }
   ```

5. `accessToken` nur im Speicher halten. Ablaufzeit als monotone Frist aus `expiresIn` berechnen und eine Sicherheitsmarge von 60 Sekunden abziehen.
6. Es gibt keinen Refresh-Flow: vor Ablauf wird mit denselben Client Credentials und dem unveränderten aktiven Scope-Satz ein neues Token angefordert.

### 2. Berechtigungsprüfung

Nach erfolgreicher Authentifizierung einmal `GET /v1/vehicles` ausführen und prüfen, ob `POLESTAR_VIN` in `data` enthalten ist. Damit werden eine falsche Account-ID, fehlende Bindung und eine falsche VIN früh und verständlich erkannt. Die Liste muss nicht in jedem Polling-Zyklus erneut geladen werden.

### 3. Generische Endpoint-Schleife und SoC-Fachableitung

Die katalogisierten Endpunkte werden sequenziell abgearbeitet. `{vin}` wird nur
in den validierten Pfadtemplates durch die URL-kodierte konfigurierte VIN ersetzt.
Jeder Request verwendet diese Header:

```http
Authorization: Bearer <accessToken>
x-client-id: <POLESTAR_ACCOUNT_ID>
Accept: application/json
```

Eine erfolgreiche JSON-Antwort wird unter einer aus dem API-Pfad abgeleiteten
MQTT-Wurzel publiziert, beispielsweise `/telemetry/battery` unter
`<base>/telemetry/battery`. Fehler werden je Endpunkt isoliert; ein Fehler bei
Location oder Charging darf Battery und die übrigen Endpunkte nicht blockieren.
Retained-Bereinigung erfolgt nur für einen fachlich erfolgreich verarbeiteten
Endpunkt.

Battery behält zusätzliche Fachlogik:

- `data.batteryChargeLevelPercentage` vorhanden und numerisch: Wert im Bereich 0 bis 100 publizieren.
- Feld fehlt: kein alter SoC darf als frisch ausgegeben werden; Warnung und Fehler-/Statuszustand publizieren.
- `meta.vin` beziehungsweise `data.vin` widerspricht der konfigurierten VIN: Antwort ablehnen.
- Der API-Zeitstempel ist `data.timestamp.seconds` plus `nanos`; er ist vom lokalen Abrufzeitpunkt zu unterscheiden.

### 4. Token- und Fehlerbehandlung

- HTTP-Timeouts explizit setzen, zum Beispiel 10 Sekunden Verbindungs- und 30 Sekunden Lesetimeout.
- Bei `401` Token einmal neu anfordern und den fachlichen Request genau einmal wiederholen.
- `400` und `403` als Konfigurations-/Berechtigungsfehler behandeln; kein aggressives Retry.
- `404` kann laut Spezifikation auch `DATA_NOT_AVAILABLE` bedeuten und ist daher ein temporärer Datenzustand.
- `429`, `500`, `502` und `503` mit begrenztem exponentiellem Backoff plus Jitter behandeln; falls `Retry-After` geliefert wird, diesen Wert beachten.
- Nach Fehlern Prozess und MQTT-Verbindung weiterlaufen lassen. Das aktuelle Muster `wait_and_die()` soll nicht übernommen werden.
- Keine Tokens, Secrets oder vollständigen Response-Header loggen. Fehlerantworten nur redigiert protokollieren.

Das bestehende Intervall von 270 Sekunden erzeugt rund 320 Zyklen pro Tag. Bei
15 katalogisierten fachlichen GET-Endpunkten sind das rund 4.800 Aufrufe zuzüglich
Token- und Fahrzeuglistenabrufen und damit weiterhin weniger als 10.000 Aufrufe
pro Client und Tag. Die tatsächliche Zahl katalogisierter Endpunkte muss in die
Rate-Limit-Bewertung einfließen; ein Intervall unter 10 Sekunden bleibt unzulässig.

## Dynamische MQTT-Ausgabe und optionale Kompatibilität

Die JSON-Struktur jedes erfolgreichen Endpunkts wird ohne feste Feldliste
rekursiv in MQTT-Topics aufgelöst. Dadurch erscheinen neue Antwortfelder und
kompatible neue Endpunkte automatisch. Topic-Änderungen gegenüber der früheren
GraphQL-Struktur sind bewusst zulässig.

Abwärtskompatibilität und spezielle Zielsysteme werden über die optionale lokale
CSV-Datei `/local-files/mqtt_topic_mapping.csv` als zusätzliche Ausgaben
konfiguriert. Ein Quellwert kann auf mehrere Ziel-Topics geschrieben werden;
die dynamischen Standard-Topics bleiben stets erhalten.

Zusätzlich empfohlen:

- `<base>/container/connected`: bestehendes LWT-Verhalten beibehalten
- `<base>/container/last_update`: nur nach einem erfolgreichen Battery-Abruf aktualisieren (Semantik klar dokumentieren)
- `<base>/container/last_error`: redigierter Fehlercode bzw. leer nach Erfolg
- `<base>/container/credentials/client_secret_expires_at`: konfiguriertes Ablaufdatum
- `<base>/container/credentials/client_secret_days_remaining`: verbleibende volle Tage
- `<base>/container/credentials/client_secret_status`: `ok`, `warning`, `critical` oder `expired`
- `<base>/carTelematics/battery/sourceTimestamp`: aus dem Telemetrie-Zeitstempel, sofern vorhanden

Nur tatsächlich vorhandene Felder werden als Nutzwerte publiziert. Fehlende
Felder werden nicht durch `null` ersetzt. Explizites JSON-`null` wird als Text
`null` retained übertragen und kennzeichnet einen vorhandenen unbekannten Wert;
dies löscht keinen retained Wert. Ein leerer String wird als zwei
Anführungszeichen (`""`) übertragen. Ausschließlich ein separater retained Publish
mit Zero-Length-Payload entfernt einen bisherigen retained Wert; diese Bereinigung
wird über das geplante Topic-Inventar gesteuert.

Für dynamische und zusätzliche Mapping-Topics gilt derselbe
[Payload-Vertrag](../doc/data-portal-data-states.md#payload-vertrag): Zahlen als
JSON-Zahlentext, Boolean als `true`/`false`, nicht leere Strings ohne zusätzliche
Anführungszeichen. Das Textformat ist nicht vollständig typerhaltend; Empfänger
müssen die Bedeutung und den erwarteten Typ des jeweiligen Felds kennen.
Ein fehlender, ungültiger oder auf `null` gesetzter SoC ist weiterhin kein
gültiger neuer Messwert. Die [Entscheidungstabelle](../doc/data-portal-data-states.md)
trennt diese fachliche Prüfung von Serialisierung und retained Bereinigung.

## Umsetzungsplan

### Phase 0: Zugang und Spike

- API-Credentials und Account-ID im Developer Portal bereitstellen.
- Mit einem kleinen, nicht eingecheckten Smoke-Test `/token`, `/v1/vehicles` und den Battery-Endpunkt gegen ein autorisiertes Fahrzeug prüfen.
- Reale Antwortform, Token-Lebensdauer, Fehlerbody und Verfügbarkeit der Daten bestätigen.

Ergebnis: Der dokumentierte Vertrag funktioniert mit den echten Credentials; offene Sandbox-/Produktionsfragen sind geklärt.

### Phase 1: HTTP-Client und Tests

- Konfigurationsmodell und Startvalidierung implementieren.
- Ablaufdatum des Client Secrets parsen, validieren und über Log/MQTT überwachen.
- `TokenProvider` mit Ablaufmarge und Re-Login implementieren.
- `list_vehicles()` und zunächst `get_battery(vin)` implementieren.
- OpenAPI-Katalog mit sicherer Pfad-Allowlist, Scope-Aggregation, lokaler Aktualisierung und gebündeltem Fallback ergänzen.
- Generischen GET-Abruf und eine fehlertolerante Endpoint-Schleife implementieren; Battery-Fachvalidierung separat beibehalten.
- Unit-Tests mit synthetisch veränderten OpenAPI-Dateien und gemockten HTTP-Antworten für neue Endpunkte, gefährliche Pfade, Teilerfolg, fehlenden SoC, abgelaufenes Token, `401`, `403`, `404`, `429` und `503` ergänzen.

Ergebnis: Die offizielle API kann ohne MQTT reproduzierbar angesprochen werden;
ein kompatibler neuer GET-Endpunkt benötigt keine neue endpunktspezifische
Client-Methode.

### Phase 2: MQTT-/openWB-Integration

- JSON-Antworten je Endpunkt dynamisch unter einer aus dem API-Pfad abgeleiteten Topic-Wurzel veröffentlichen.
- Optionale CSV-Mappings für zusätzliche Kompatibilitäts- und Zielsystem-Topics anwenden.
- Change Detection beibehalten; Statuszeitpunkt trotzdem korrekt behandeln.
- openWB-Ausgabe gegen fehlenden oder ungültigen SoC absichern.
- Fehlerstatus und Logging ergänzen.

Ergebnis: Neue Endpunkte und Felder erscheinen automatisch; bestehende
Verbraucher können bei Bedarf über lokale zusätzliche Mappings weiter versorgt
werden.

### Phase 3: Container und Dokumentation

- Die versionierte Deployment-Vorlage `docker-compose_example.yml` auf die neuen Credential-Variablen und sichere Platzhalter umstellen.
- Das Ablaufdatum des Client Secrets in Deployment-Vorlage, README und Betriebsanleitung aufnehmen.
- Die ignorierte lokale `docker-compose.yml` ausschließlich für den End-to-End-Test verwenden und nicht als auszuliefernde Konfiguration behandeln.
- Den bestehenden Workflow `.github/workflows/docker-image.yml` für Build und Veröffentlichung des neuen Images verifizieren.
- README und Synology-Anleitung aktualisieren.
- Gebündelte OpenAPI-Datei unter `api/` in das Image aufnehmen und den lokalen Override unter `local-files` dokumentieren.
- Alten E-Mail-/Passwort-, PKCE-, Refresh-Token- und GraphQL-Code entfernen.
- Container lokal mit HTTP-Mocks testen; danach manueller Smoke-Test mit echten Credentials.
- Vor dem Release einen manuellen Security-Code-Review sowie automatisierte
  Code-, Dependency-, Secret-, Container- und GitHub-Workflow-Scans als
  verpflichtendes Gate durchführen.

Ergebnis: Ein schlankes, dokumentiertes und gehärtetes MVP-Image ohne
Abhängigkeit von der inoffiziellen API.

## Tests und Abnahmekriterien

Der MVP ist abgenommen, wenn:

- der Container ausschließlich mit offiziellen API-Credentials startet,
- ein fehlendes oder ungültiges Secret-Ablaufdatum den Start mit einer verständlichen Konfigurationsmeldung verhindert,
- die Anwendung bei 30, 14, 7, 3, 1 und 0 verbleibenden Tagen eine entprellte Warnung erzeugt und den Credential-Status retained über MQTT bereitstellt,
- ein Token mit genau den deduplizierten Scopes aller katalogisierten Endpunkte bezogen und vor Ablauf erneuert wird,
- eine nicht autorisierte VIN bereits beim Start verständlich gemeldet wird,
- ein synthetisch ergänzter kompatibler GET-Endpunkt ohne Codeänderung katalogisiert, abgerufen und dynamisch publiziert wird,
- ungültige Methoden, Pfade oder Serverangaben aus einer ausgetauschten Spezifikation nicht ungeprüft ausgeführt werden,
- der Fehler eines einzelnen Endpunkts die übrigen Endpunkte desselben Zyklus nicht blockiert,
- ein erfolgreicher Battery-Abruf den SoC retained mit QoS 1 dynamisch und optional über zusätzliche CSV-Mappings publiziert,
- openWB bei aktivierter Option denselben validierten SoC erhält,
- ein einmaliges `401` automatisch durch Token-Neubezug geheilt wird,
- temporäre API-Ausfälle weder Credentials offenlegen noch eine enge Restart-Schleife erzeugen,
- fehlende Telemetriedaten nicht als gültiger neuer SoC erscheinen,
- Unit-Tests ohne Netzwerkzugriff laufen und der reale Smoke-Test dokumentiert ist.

## Entscheidungen und offene Punkte

Für den MVP empfohlen entschieden:

- Scopes werden ausschließlich aus allen validierten, katalogisierten OpenAPI-GET-Operationen abgeleitet und deterministisch gebündelt
- die konfigurierte `POLESTAR_API_BASE_URL` bleibt maßgeblich; `servers` aus einer lokalen Spezifikation ändert das Request-Ziel nicht automatisch
- kompatible lesende Fahrzeugendpunkte werden generisch verarbeitet; Schreiboperationen bleiben ausgeschlossen
- alle erlaubten GET-Endpunkte des Katalogs werden berücksichtigt, einschließlich Location; keine optionale Auswahl oder Ausschlussliste (Nutzervorgabe vom 2026-10-10)
- VIN bleibt explizite Konfiguration; `/v1/vehicles` dient der Validierung
- dynamische Topics folgen der REST-JSON-Struktur; zusätzliche Kompatibilität ist Aufgabe des lokalen CSV-Mappings
- Token und Secret werden nicht persistent gespeichert
- das bekannte Secret-Ablaufdatum wird konfiguriert und überwacht; es wird nicht mit der Access-Token-Ablaufzeit verwechselt
- Polling bleibt standardmäßig bei 270 Sekunden

Vor der Implementierung mit echten Credentials zu verifizieren:

1. Ist die dokumentierte URL nur eine Sandbox oder der vorgesehene produktive Endpunkt für dieses Projekt?
2. Ist die im Markdown genannte Account-ID installationsspezifisch oder lediglich die aktuell ausgestellte ID und damit kein allgemeiner Default?
3. Welche konkrete Token-Lebensdauer liefert der Dienst und gibt es undokumentierte Rate-Limit-Header?
4. Wie sehen reale `404 DATA_NOT_AVAILABLE`- und `429`-Antworten aus?

Diese Punkte blockieren die Struktur des Rewrites nicht; sie sollten im Phase-0-Spike geklärt werden, bevor das MVP als produktionsreif gilt.
