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

## Data-Portal-Ausgabe: dynamischer Topic-Baum

Für die Battery-Ausgabe ist die Wurzel
`<MQTT_BASE_TOPIC>/telemetry/battery` festgelegt. Die Programmsteuerung soll dem
Publisher die vollständige, fachlich validierte Battery-Antwort einschließlich
`data` und `meta` mit dieser Wurzel übergeben. Der Publisher unterstützt diesen
Aufruf bereits; der lokale Einmallauf `runonce-DataPortalAPI` verwendet ihn.
Die Einbindung in die dauerhafte Programmsteuerung steht noch aus.

Alle Objekt-Ebenen bleiben erhalten. Jeder JSON-Schlüssel wird ein eigenes
Topic-Segment; Array-Elemente erhalten ihren Index ab `0`. Skalare Blätter werden
retained mit QoS 1 publiziert. Objekte und Arrays selbst erzeugen keinen Payload,
leere Objekte und Arrays keine Blatt-Topics. Groß-/Kleinschreibung bleibt erhalten.
Sonderzeichen in Schlüsseln werden pro Segment UTF-8-prozentkodiert, beispielsweise
`charge/status` zu `charge%2Fstatus`; ein leerer Schlüssel wird `%EMPTY`.

Bei `MQTT_BASE_TOPIC=polestar2` ergeben sich beispielsweise:

| JSON-Pfad in der Battery-Antwort | Dynamisches MQTT-Topic |
| --- | --- |
| `data.batteryChargeLevelPercentage` | `polestar2/telemetry/battery/data/batteryChargeLevelPercentage` |
| `data.timestamp.seconds` | `polestar2/telemetry/battery/data/timestamp/seconds` |
| `data.vin` | `polestar2/telemetry/battery/data/vin` |
| `meta.vin` | `polestar2/telemetry/battery/meta/vin` |
| `meta.domain` | `polestar2/telemetry/battery/meta/domain` |

`data` wird nicht ausgepackt und `meta` nicht verworfen. Identifizierende Felder
wie `data.vin`, `meta.vin` oder eine Ereignis-ID werden als gelieferte Nutzwerte
mitpubliziert, sofern vorhanden. Es gibt keine automatische Anonymisierung des
MQTT-Payloads. Die VIN wird nicht zusätzlich als Bestandteil der Topic-Wurzel
verwendet. Echte VINs und andere vertrauliche Werte gehören weiterhin nicht in
Logs, Dokumentationsbeispiele oder eingecheckte Fixtures.

Die Ausgabe verwendet keine feste Telemetriefeldliste. Ein künftig geliefertes
Blatt `data.futureTelemetry.newScalar` erscheint automatisch unter
`<MQTT_BASE_TOPIC>/telemetry/battery/data/futureTelemetry/newScalar`; dieselbe
Regel gilt für neue Metadaten. Nur die validierte fachliche Battery-Antwort wird
übergeben, keine Token-Antwort, Zugangsdaten, HTTP-Header oder Fehlerantwort.

Der dynamische Baum liegt vollständig unter `telemetry/battery`. Auch ein
JSON-Schlüssel `container` bleibt dort und erzeugt keinen Betriebsstatus unter
`<MQTT_BASE_TOPIC>/container`. Der Schutz dieses separaten Betriebsbereichs vor
Mapping-Zielen ist eine eigene offene Migrationsaufgabe.

Mapping-Quellpfade beginnen am ursprünglichen JSON, beispielsweise
`data.batteryChargeLevelPercentage`, ohne MQTT-Basis oder `telemetry.battery`.
Zusätzliche Mapping-Ziele ändern weder diese Wurzel noch den dynamischen Baum.
Die Regeln zur Behandlung ungültiger oder veralteter Daten und zur späteren
Bereinigung retained gespeicherter Topics werden in separaten Schritten ergänzt.

## Data-Portal-Mapping: JSON-Pfad zu zusätzlichem MQTT-Topic

`source_path` bezeichnet einen Pfad im ursprünglichen JSON in Punktnotation,
kein MQTT-Topic. Beispielsweise ordnet diese CSV-Zeile den Wert `77` aus
`{"carTelematics":{"battery":{"soc":77}}}` einem zusätzlichen Ziel zu:

```csv
source_path,target_topic
carTelematics.battery.soc,absolute:openWB/LP1/SoC
```

Das Ziel ist `openWB/LP1/SoC`. Die dynamischen Topics aus demselben JSON bleiben
erhalten. Für die tatsächliche Data-Portal-Battery-Antwort heißt der SoC-Quellpfad
`data.batteryChargeLevelPercentage`; das Beispiel oben setzt die gezeigte
JSON-Struktur voraus und führt keinen Alias für API-Felder ein.
Ein Punkt trennt JSON-Schlüssel. Sonderzeichen werden mit Backslash maskiert:
`\.` steht für einen Punkt im Schlüssel, `\\` für einen Backslash und `\/` für
einen Slash. `\e` bezeichnet einen leeren Schlüssel und muss das gesamte Segment
bilden. Zum Beispiel ist `data.\e` der leere Schlüssel unter `data`, während
`data.\\e` den wörtlichen Schlüssel `\e` bezeichnet. Andere Escape-Sequenzen,
ein abschließender Backslash und leere Segmente wie `data..soc` werden abgelehnt.

Bei einem Array bezeichnet ein numerisches Segment den Index ab `0`, etwa
`data.batteries.0.soc`. Zulässig sind ASCII-Ziffern ohne Vorzeichen oder führende
Nullen (außer `0`). Bei einem Objekt ist dasselbe Segment ein gewöhnlicher
Schlüssel: `data.0` liest dort den Schlüssel `"0"`. Fehlende Indizes, negative
Indizes, falsche Typen und nicht skalare Ergebnisse erzeugen keine zusätzliche
Ausgabe. Verschachtelte Arrays funktionieren ebenso, zum Beispiel `data.0.1`.
Pfade beziehen sich immer auf die JSON-Wurzel, ohne `$`-Präfix; Wildcards,
Array-Klammernotation und Filterausdrücke werden nicht ausgewertet. Sonstige
Zeichen in einem Segment sind wörtliche Bestandteile des Schlüssels.

Beispiele (die jeweiligen Quellfelder müssen im JSON vorhanden sein):

```csv
source_path,target_topic
data.batteryChargeLevelPercentage,absolute:openWB/LP1/SoC
data.batteries.0.soc,extra/first-battery-soc
data.sensor\.value,extra/sensor-value
data.charge\/status,extra/charge-status
data.\\e,extra/literal-backslash-e
data.\e,extra/empty-key
```

Die Backslashes stehen so in der CSV; es erfolgt keine zusätzliche
MQTT-Prozentdekodierung der Quellpfade. CSV-Felder mit Komma oder doppelten
Anführungszeichen müssen zusätzlich nach CSV-Regeln zitiert werden (Anführungszeichen
im zitierten Feld verdoppeln). Äußerer Leerraum eines CSV-Feldes wird entfernt;
Schlüssel mit äußerem Leerraum am gesamten Pfadrand sind damit nicht adressierbar.

Die neue Publisher-Komponente liest die skalaren Werte direkt aus dem JSON und
publiziert sie zusätzlich retained mit QoS 1. Dazu wird die CSV mit
`parse_topic_mapping_csv()` eingelesen, mit `resolve_topic_mapping()` auf die
konfigurierte MQTT-Basis bezogen und als `mapping` an `publish_json_topics()`
übergeben. Die dynamische Topic-Wurzel kann von dieser Basis abweichen.
`load_topic_mapping(config.mqtt_topic_mapping_file, config.mqtt_base_topic)`
fasst Dateiladen, CSV-Prüfung und Zielauflösung zusammen. Der Standardpfad ist
`/local-files/mqtt_topic_mapping.csv`; `MQTT_TOPIC_MAPPING_FILE` kann ihn ändern.
Eine fehlende Datei liefert ein leeres Mapping, sodass nur dynamische Topics
publiziert werden. Eine reine Kopfzeile ist ebenfalls gültig. Eine vorhandene
leere Datei, ungültige Spalten oder CSV-Zeilen, ungültiges UTF-8 und Lesefehler
werden als `TopicMappingError` gemeldet. Meldungen enthalten keine Dateipfade
oder Zeileninhalte; bei fehlerhaften Zeilen wird die physische Zeilennummer
angegeben. UTF-8 mit und ohne BOM wird unterstützt.
Der lokale Einmallauf `./run_local.sh runonce-DataPortalAPI` nutzt diese Funktionen
bereits gemeinsam und wartet auf die MQTT-Bestätigungen. Die Einbindung in die
dauerhafte Programmsteuerung folgt in einem späteren Schritt.

Fehlende Quellpfade sowie Objekt- oder Array-Werte erzeugen keine zusätzliche
Ausgabe. Vorhandene skalare Werte verwenden dieselbe Serialisierung wie die
dynamische Ausgabe, einschließlich `0`, `false`, leerer Strings und `null`.
Mapping-Ziele dürfen keine dynamischen Topics oder Ziele anderer Quellen
überschreiben; solche Konflikte werden vor dem ersten Publish abgelehnt.

Für `MQTT_BASE_TOPIC=polestar2` gelten folgende Regeln:

| `target_topic` in der CSV | Aufgelöstes MQTT-Topic |
| --- | --- |
| `carTelematics/battery/soc` | `polestar2/carTelematics/battery/soc` |
| `absolute:homeassistant/polestar/soc` | `homeassistant/polestar/soc` |
| `absolute:/custom/soc` | `/custom/soc` |

`absolute:` kennzeichnet ein Ziel ohne Basis-Präfix und gehört nicht zum
ausgegebenen Topic. Ein führender Slash allein ist keine Absolut-Kennzeichnung;
er wird nur nach `absolute:` als tatsächlicher Bestandteil des Topics akzeptiert.
Relative Ziele benötigen eine nicht leere Basis; abschließende Slashes der Basis
werden vor dem Zusammenfügen entfernt. Leere Ziele werden abgelehnt.
Mehrere identische aufgelöste Ziele derselben Quelle werden zusammengefasst.
