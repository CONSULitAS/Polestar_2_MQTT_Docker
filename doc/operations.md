# Betrieb

## Start mit Docker
1. `docker-compose_example.yml` nach `docker-compose.yml` kopieren.
2. `.env.example` nach `.env` kopieren und Data-Portal-Zugangsdaten setzen.
3. `local-files/` für den Containerbenutzer (UID 999) beschreibbar machen.
4. Mit `docker compose up --build` das Image dieses Branches bauen und starten.

Der reguläre Start führt aktuell einen Data-Portal-Einmallauf aus und beendet sich.
Die Vorlage deaktiviert automatische Neustarts. Dauerhaftes Polling, Container-LWT
und separate openWB-Weiterleitung bleiben offene Migrationsaufgaben.

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
