# MVP-Konzept: offizielle Polestar Data Portal API

## Ziel und Abgrenzung

Der erste Rewrite-Schritt ersetzt die bisherige inoffizielle Polestar-ID-/GraphQL-Anbindung durch die offizielle M2M-API. Der MVP soll:

1. sich per OAuth2 Client Credentials authentifizieren,
2. die Berechtigung für die konfigurierte VIN prüfen,
3. den Batterie-SoC zyklisch abrufen,
4. den SoC weiterhin über MQTT und optional an openWB veröffentlichen.

Nicht Teil des MVP sind weitere Telemetriedomänen, Fahrzeug-Stammdaten, Schreiboperationen, eine automatische Migration aller bisherigen MQTT-Felder und Third-Party-Delegation. Die Architektur soll diese Erweiterungen danach ohne erneuten Umbau ermöglichen.

## Ausgangslage und API-Vertrag

Die bisherige Implementierung simuliert einen Benutzer-Login mit E-Mail, Passwort und PKCE und ruft anschließend die nicht offizielle GraphQL-API `mystar-v2` auf. Die offizielle API arbeitet anders:

- Basis-URL: `https://pc-api.polestar.com/eu-north-1/data-portal/m2m`
- Authentifizierung: `POST /token` mit `clientId`, `clientSecret` und optionalem `scope`
- Token-Antwort: `accessToken`, `expiresIn`, `tokenType`; es gibt laut Spezifikation keinen Refresh-Token
- Fahrzeugliste: `GET /v1/vehicles`
- SoC: `GET /v1/vehicles/{vin}/telemetry/battery`
- Pflicht-Header an den fachlichen Endpunkten: `Authorization: Bearer ...` und `x-client-id: <Account-ID>`
- Für Battery ist der Scope `pdp-telemetry/battery` erforderlich.
- Der gesuchte Wert steht in `data.batteryChargeLevelPercentage`. Alle Telemetriefelder außer `vin` können fehlen.
- Rate Limit: maximal 10.000 Aufrufe pro Client und Tag.

Wichtig ist die begriffliche Trennung zweier IDs: `clientId` ist Teil der OAuth-Credentials; `x-client-id` ist die im Developer Portal gebundene eigene User-/Account-ID. Im Code und in der Konfiguration müssen sie deshalb unterschiedlich benannt werden.

## Zielarchitektur

Die bisherige monolithische Datei sollte beim Rewrite in kleine Verantwortungsbereiche zerlegt werden:

```text
Konfiguration
     |
     v
TokenProvider ----> POST /token
     |
     v
PolestarDataPortalClient ----> GET /v1/vehicles
     |                         GET /v1/vehicles/{vin}/telemetry/battery
     v
SoC-Anwendungsdienst
     |-----------------------> MQTT
     `-----------------------> openWB (optional)
```

Empfohlene Module:

- `config.py`: Umgebungsvariablen lesen und beim Start vollständig validieren
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
2. `POST /token` als JSON oder Form-Body senden:

   ```json
   {
     "clientId": "...",
     "clientSecret": "...",
     "scope": "pdp-telemetry/battery"
   }
   ```

3. `accessToken` nur im Speicher halten. Ablaufzeit als monotone Frist aus `expiresIn` berechnen und eine Sicherheitsmarge von 60 Sekunden abziehen.
4. Es gibt keinen Refresh-Flow: vor Ablauf wird mit denselben Client Credentials ein neues Token angefordert.

### 2. Berechtigungsprüfung

Nach erfolgreicher Authentifizierung einmal `GET /v1/vehicles` ausführen und prüfen, ob `POLESTAR_VIN` in `data` enthalten ist. Damit werden eine falsche Account-ID, fehlende Bindung und eine falsche VIN früh und verständlich erkannt. Die Liste muss nicht in jedem Polling-Zyklus erneut geladen werden.

### 3. SoC-Abruf

`GET /v1/vehicles/{vin}/telemetry/battery` mit URL-kodierter VIN und diesen Headern senden:

```http
Authorization: Bearer <accessToken>
x-client-id: <POLESTAR_ACCOUNT_ID>
Accept: application/json
```

Die Antwort wird strikt, aber tolerant ausgewertet:

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

Das bestehende Intervall von 270 Sekunden erzeugt rund 320 Battery-Aufrufe pro Tag und liegt weit unter dem Limit. Token- und einmaliger Vehicle-Aufruf kommen hinzu. Ein Intervall unter 10 Sekunden sollte durch Validierung verhindert werden, weil bereits ein einzelner dauerhaft laufender Abruf sonst das Tageslimit überschreiten kann.

## MQTT-Kompatibilität

Der wichtigste bestehende Consumer (`Node-RED_interface.json`) hört auf:

```text
<MQTT_BASE_TOPIC>/carTelematics/battery/batteryChargeLevelPercentage
```

Dieser Topic-Vertrag sollte im MVP unverändert bleiben, obwohl die Quelle jetzt REST statt GraphQL ist. Dadurch müssen Node-RED und openWB für den API-Wechsel nicht gleichzeitig migriert werden. Der numerische Payload bleibt ebenfalls unverändert.

Zusätzlich empfohlen:

- `<base>/container/connected`: bestehendes LWT-Verhalten beibehalten
- `<base>/container/last_update`: nur nach einem erfolgreichen Battery-Abruf aktualisieren (Semantik klar dokumentieren)
- `<base>/container/last_error`: redigierter Fehlercode bzw. leer nach Erfolg
- `<base>/container/credentials/client_secret_expires_at`: konfiguriertes Ablaufdatum
- `<base>/container/credentials/client_secret_days_remaining`: verbleibende volle Tage
- `<base>/container/credentials/client_secret_status`: `ok`, `warning`, `critical` oder `expired`
- `<base>/carTelematics/battery/sourceTimestamp`: aus dem Telemetrie-Zeitstempel, sofern vorhanden

Nur tatsächlich vorhandene neue Felder sollten publiziert werden. Ein fehlendes Feld darf nicht als `null` retained werden, solange nicht bewusst entschieden wurde, damit einen alten retained Wert zu löschen.

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
- `list_vehicles()` und `get_battery(vin)` implementieren.
- Unit-Tests mit gemockten HTTP-Antworten für Erfolg, fehlenden SoC, abgelaufenes Token, `401`, `403`, `404`, `429` und `503` ergänzen.

Ergebnis: Die offizielle API kann ohne MQTT reproduzierbar angesprochen und getestet werden.

### Phase 2: MQTT-/openWB-Integration

- SoC auf den bestehenden MQTT-Topic abbilden.
- Change Detection beibehalten; Statuszeitpunkt trotzdem korrekt behandeln.
- openWB-Ausgabe gegen fehlenden oder ungültigen SoC absichern.
- Fehlerstatus und Logging ergänzen.

Ergebnis: Bestehende Verbraucher erhalten den SoC ohne Topic-Änderung.

### Phase 3: Container und Dokumentation

- Die versionierte Deployment-Vorlage `docker-compose_example.yml` auf die neuen Credential-Variablen und sichere Platzhalter umstellen.
- Das Ablaufdatum des Client Secrets in Deployment-Vorlage, README und Betriebsanleitung aufnehmen.
- Die ignorierte lokale `docker-compose.yml` ausschließlich für den End-to-End-Test verwenden und nicht als auszuliefernde Konfiguration behandeln.
- Den bestehenden Workflow `.github/workflows/docker-image.yml` für Build und Veröffentlichung des neuen Images verifizieren.
- README und Synology-Anleitung aktualisieren.
- Alten E-Mail-/Passwort-, PKCE-, Refresh-Token- und GraphQL-Code entfernen.
- Container lokal mit HTTP-Mocks testen; danach manueller Smoke-Test mit echten Credentials.

Ergebnis: Ein schlankes, dokumentiertes MVP-Image ohne Abhängigkeit von der inoffiziellen API.

## Tests und Abnahmekriterien

Der MVP ist abgenommen, wenn:

- der Container ausschließlich mit offiziellen API-Credentials startet,
- ein fehlendes oder ungültiges Secret-Ablaufdatum den Start mit einer verständlichen Konfigurationsmeldung verhindert,
- die Anwendung bei 30, 14, 7, 3, 1 und 0 verbleibenden Tagen eine entprellte Warnung erzeugt und den Credential-Status retained über MQTT bereitstellt,
- ein Token mit minimalem Battery-Scope bezogen und vor Ablauf erneuert wird,
- eine nicht autorisierte VIN bereits beim Start verständlich gemeldet wird,
- ein erfolgreicher Abruf den SoC retained mit QoS 1 auf dem bisherigen Topic publiziert,
- openWB bei aktivierter Option denselben validierten SoC erhält,
- ein einmaliges `401` automatisch durch Token-Neubezug geheilt wird,
- temporäre API-Ausfälle weder Credentials offenlegen noch eine enge Restart-Schleife erzeugen,
- fehlende Telemetriedaten nicht als gültiger neuer SoC erscheinen,
- Unit-Tests ohne Netzwerkzugriff laufen und der reale Smoke-Test dokumentiert ist.

## Entscheidungen und offene Punkte

Für den MVP empfohlen entschieden:

- minimaler Scope nur `pdp-telemetry/battery`
- VIN bleibt explizite Konfiguration; `/v1/vehicles` dient der Validierung
- bestehender SoC-MQTT-Topic bleibt kompatibel
- Token und Secret werden nicht persistent gespeichert
- das bekannte Secret-Ablaufdatum wird konfiguriert und überwacht; es wird nicht mit der Access-Token-Ablaufzeit verwechselt
- Polling bleibt standardmäßig bei 270 Sekunden

Vor der Implementierung mit echten Credentials zu verifizieren:

1. Ist die dokumentierte URL nur eine Sandbox oder der vorgesehene produktive Endpunkt für dieses Projekt?
2. Ist die im Markdown genannte Account-ID installationsspezifisch oder lediglich die aktuell ausgestellte ID und damit kein allgemeiner Default?
3. Welche konkrete Token-Lebensdauer liefert der Dienst und gibt es undokumentierte Rate-Limit-Header?
4. Wie sehen reale `404 DATA_NOT_AVAILABLE`- und `429`-Antworten aus?

Diese Punkte blockieren die Struktur des Rewrites nicht; sie sollten im Phase-0-Spike geklärt werden, bevor das MVP als produktionsreif gilt.
