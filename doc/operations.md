# Betrieb

## Start mit Docker
1. `docker-compose_example.yml` nach `docker-compose.yml` kopieren.
2. `.env.example` nach `.env` kopieren und Data-Portal-Zugangsdaten setzen.
3. `local-files/` für den Containerbenutzer (UID 999) beschreibbar machen.
4. Mit `docker compose up --build` das Image dieses Branches bauen und starten.

Der reguläre Start führt aktuell einen Data-Portal-Einmallauf aus und beendet sich.
Die Vorlage deaktiviert automatische Neustarts. Betriebsstatus und Offline-LWT
sind im Einmallauf aktiv; dauerhaftes Polling und separate openWB-Weiterleitung
bleiben offene Migrationsaufgaben.

## Lokaler Start
1. `.env` und `.env_local` aus den Beispiel-Dateien erzeugen und Werte anpassen.
2. `./run_local.sh runonce` ausführen; `./run_local.sh` verwendet denselben Einmallauf.

`./run_local.sh auth-check` prüft ausschließlich den Token-Endpunkt.
`runonce-DataPortalAPI` und `soc-check` bleiben Aliase für den Einmallauf mit MQTT-Ausgabe.

## Relevante Umgebungsvariablen
- Data Portal: `POLESTAR_ACCOUNT_ID`, `POLESTAR_CLIENT_ID`,
  `POLESTAR_CLIENT_SECRET`, `POLESTAR_CLIENT_SECRET_EXPIRES_AT`, `POLESTAR_VIN`
- MQTT: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`, `MQTT_BASE_TOPIC`
- Lokale Dateien: `POLESTAR_OPENAPI_FILE`, `MQTT_TOPIC_MAPPING_FILE`, `MQTT_TOPIC_STATE_FILE`

## Betriebschecks
- Einmallauf endet nach bestätigten MQTT-Publikationen mit Exit-Code 0.
- Logs prüfen: `docker compose logs polestar2mqtt`.
- Bei Loginfehlern Data-Portal-Credentials und Ablaufdatum prüfen.
- Bei MQTT-Fehlern Broker-Adresse, Port und Authentifizierung prüfen.
- Bei Inventarfehlern Schreibrechte des Zustandsverzeichnisses prüfen.

## MQTT-Betriebsstatus des Einmallaufs

Alle folgenden Topics liegen unter `<MQTT_BASE_TOPIC>/container`, werden mit
QoS 1 und Retain veröffentlicht und bleiben außerhalb des Telemetrie-Inventars.

| Topic | Bedeutung |
| --- | --- |
| `connected` | `online` nach MQTT-Verbindungsaufbau; bestätigt `offline` vor normalem Disconnect. Bei Verbindungsverlust veröffentlicht der Broker das vor CONNECT konfigurierte `offline`-LWT. |
| `last_update` | ISO-8601 in UTC (`Z`): Zeitpunkt des letzten fachlich gültigen Battery-Abrufs. Bei ungültiger Battery oder API-Ausfall unverändert; weder Messzeit noch Zustellbestätigung. |
| `last_error` | Aktive lokale Fehlercodes, durch Semikolon getrennt; ohne Fehler leere Payload zum Löschen des vorherigen retained Fehlers. |
| `last_exception` | Ausschließlich Exception-Klassennamen, keine Exception-Texte, HTTP-Bodies, Credentials oder Fahrzeugkennungen; wird nach fehlerfreiem Abruf geleert. |
| `credentials/client_secret_expires_at` | Konfigurierter Ablaufzeitpunkt als ISO-8601 in UTC. |
| `credentials/client_secret_days_remaining` | Nicht negative Anzahl verbleibender voller Tage. |
| `credentials/client_secret_status` | `ok`, `warning`, `critical` oder `expired` gemäß bestehendem Ablaufmonitor. |

Fehlerpriorität: `publication_failed` vor `api_failed` (Token-/Fahrzeuglistenfehler)
oder `api_partial` (einzelne Endpunkte), danach `credential_expired` beziehungsweise
`credential_expiring` und gegebenenfalls `source_time_unknown`. Alle aktiven Ursachen
bleiben sichtbar. Ab 14 verbleibenden Tagen erscheint die Credential-Warnung auch
im Fehlerstatus; ein erfolgreicher Battery-Abruf löscht sie nicht. Fehlende Quellzeit
bedeutet unbekannte Messzeit und verhindert keinen gültigen Abrufzeitpunkt.
Detaillierte Endpunktfehler stehen weiterhin im jeweiligen `log`-Unterbaum.

Der Einmallauf liest zunächst die API und verbindet sich danach mit MQTT. Auch ein
Token-/Fahrzeuglistenfehler wird anschließend als Betriebsstatus veröffentlicht,
sofern MQTT erreichbar ist. `online` bezeichnet daher die MQTT-Publikationsphase;
die MQTT-Verbindung vor dem API-Abruf wird erst mit M7 eingeführt. Ungültige lokale
Konfiguration, Inventar- oder Topic-Konflikte können den Lauf vor MQTT beenden.
Bei Publikationsfehlern wird die Fehlerausgabe versucht; ohne erreichbaren Broker
ist keine Zustellung garantiert. Kann `offline` nicht bestätigt werden, wird die
Verbindung ohne reguläres MQTT-DISCONNECT geschlossen, damit das LWT wirksam bleibt.

Ein abgeschlossener Einmallauf steht erwartungsgemäß auf `offline`. Ein neuer Lauf
veröffentlicht Status und Credential-Werte erneut. Automatischer Reconnect,
Signalbehandlung, tägliche Prüfungen im Dauerbetrieb und openWB-Fehlerpriorisierung
bleiben in M6.3/M7 offen. Der Einmallauf vergleicht keine Quellzeit-Historie.
