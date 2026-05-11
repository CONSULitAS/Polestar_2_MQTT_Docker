# Dokumentation

Dieser Ordner enthält die technische Projektdokumentation ergänzend zur `README.md` im Repository-Root.

## Inhalte
- `architecture.md`: Systemaufbau, Datenfluss und Komponenten
- `operations.md`: Betrieb, Konfiguration und Troubleshooting

## Zielgruppe
- Betreiber des Docker-Containers
- Entwickler, die Login-, API- oder MQTT-Logik erweitern

## Testen
- Unit-Tests werden mit `pytest` ausgeführt.
- Einstieg lokal über `./run_tests.sh` im Repository-Root.
- Der aktuelle Fokus liegt auf Auth-, Payload- und MQTT/API-Helferlogik ohne echte Netzwerkverbindungen.
