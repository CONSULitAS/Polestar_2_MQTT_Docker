# Betrieb

## Start mit Docker
1. `docker-compose_example.yml` nach `docker-compose.yml` kopieren.
2. `.env.example` nach `.env` kopieren und Werte setzen.
3. Optional `local-files/graphql_queries.py_sample` nach `local-files/graphql_queries.py` kopieren.
4. Starten mit `docker compose up -d`.

## Lokaler Start (ohne Container)
1. `.env` und `.env_local` aus den Beispiel-Dateien erzeugen.
2. Werte anpassen.
3. `./run_local.sh` ausführen.

## Relevante Umgebungsvariablen
- Polestar: `POLESTAR_EMAIL`, `POLESTAR_PASSWORD`, `POLESTAR_VIN`, `POLESTAR_CYCLE`
- MQTT: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`, `MQTT_BASE_TOPIC`
- Optional OpenWB: `OPENWB_PUBLISH`, `OPENWB_HOST`, `OPENWB_PORT`, `OPENWB_LP_NUM`

## Betriebschecks
- Container läuft: `docker compose ps`
- Logs prüfen: `docker compose logs -f polestar2mqtt`
- MQTT-LWT-Topic beobachten: `<MQTT_BASE_TOPIC>/container/connected`

## Häufige Fehlerbilder
- Login schlägt fehl: Credentials prüfen, Polestar-Kontozugang im Web testen.
- Keine MQTT-Nachrichten: Broker-Adresse/Port/Authentifizierung prüfen.
- Keine lokalen GraphQL-Overrides: Existenz und Funktionsnamen in `local-files/graphql_queries.py` prüfen.
