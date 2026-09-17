# Data Portal: Datenzustände und Ausgabeentscheidungen

Diese Tabelle legt das Zielverhalten für M6/M7 fest. Sie ist keine Aussage,
dass Statusausgabe, Topic-Bereinigung und Zeitstempelvergleich bereits umgesetzt
sind. Sie gilt für dynamische Telemetrie-Topics und zusätzliche Mapping-Ziele
gleichermaßen. HTTP 200 allein macht eine Antwort nicht zu einem gültigen Messwert.

## Voraussetzungen und Reihenfolge

Eine akzeptierte Battery-Antwort besitzt die erwartete Objektstruktur, eine zur
Konfiguration passende Antwort-VIN und einen endlichen numerischen SoC zwischen
0 und 100. Boolean, numerische Strings und `null` sind kein gültiger SoC.
Ein vorhandener Quellzeitstempel muss gültig sein; fehlender oder explizit auf
`null` gesetzter Zeitstempel bedeutet „Quellzeit unbekannt“.

Zuerst werden Transport und Antwort validiert, danach die Quellzeit geprüft.
Erst bei einer akzeptierten Antwort gelten die Regeln für einzelne optionale
Felder. Beispielsweise führt ein fehlender SoC zur Ablehnung der gesamten
Antwort, auch wenn andere Felder vorhanden sind. Feldlöschungen sind in diesem
Fall nicht zulässig. Ungültige MQTT-Ziele verhindern weiterhin alle Publishes.

## Entscheidungstabelle

Die genannten Statuscodes sind geplante redigierte Zustände für
`<base>/container/last_error`. „Aktualisieren“ bei openWB setzt eine aktivierte
separate Weiterleitung voraus und berücksichtigt Change Detection und Reconnect.

| Fall | Telemetrie und zusätzliche Mapping-Ausgabe | Bisherige retained Werte | Status und `last_update` | Separate openWB-Ausgabe |
| --- | --- | --- | --- | --- |
| Transportfehler, Timeout oder HTTP-Fehler nach ausgeschöpften Retries | Keine Messwerte publizieren | Beibehalten; keine Bereinigung | Passender Transport-/HTTP-Fehler, `last_update` unverändert | Nicht aktualisieren |
| HTTP 200 mit ungültigem JSON, falscher Struktur oder abweichender VIN | Gesamte Antwort ablehnen | Beibehalten; keine Bereinigung | `invalid_response`, `last_update` unverändert | Nicht aktualisieren |
| SoC fehlt, ist `null`, nicht numerisch oder außerhalb des gültigen Bereichs | Gesamte Antwort ablehnen | Beibehalten, insbesondere alten SoC nicht als frisch publizieren | `invalid_soc`, `last_update` unverändert | Nicht aktualisieren |
| Vorhandener Quellzeitstempel ist ungültig | Gesamte Antwort ablehnen | Beibehalten; keine Bereinigung | `invalid_timestamp`, `last_update` unverändert | Nicht aktualisieren |
| Gültige Antwort mit neuer Quellzeit oder ohne vorherigen Vergleichswert | Vorhandene Werte dynamisch und gemäß Mapping publizieren | Aktuelle Werte ersetzen; nicht mehr erzeugte verwaltete Topics gemäß Inventar löschen | Datenfehler zurücksetzen; `last_update` auf erfolgreichen Abrufzeitpunkt setzen | Validierten SoC aktualisieren |
| Gültige Teilantwort: SoC gültig, optionale Felder fehlen | Vorhandene Werte publizieren; fehlende Quellen erzeugen keine zusätzlichen Publishes | Nur nicht mehr erzeugte verwaltete Topics gemäß Inventar löschen | Kein Datenfehler allein wegen optionaler Felder; `last_update` aktualisieren | Validierten SoC aktualisieren |
| Optionales skalares Feld ist explizit `null` | Vorhandenes `null` als unbekannten Wert publizieren, auch über sein Mapping | Bisherigen Wert dieses Topics durch `null` ersetzen; nicht als Löschung behandeln | Kein Datenfehler allein wegen optionalem `null`; `last_update` aktualisieren | Nur den gültigen SoC weitergeben; `null` nie als SoC senden |
| Gültige Antwort ohne Quellzeit (fehlend oder `null`) | Werte publizieren, keinen Messzeitpunkt erfinden | Aktuelle Werte ersetzen; Feldregeln und Inventarbereinigung anwenden | `source_time_unknown`; `last_update` als Abrufzeit aktualisieren | Validierten SoC aktualisieren; keine Frischegarantie ableiten |
| Quellzeit identisch mit der zuletzt akzeptierten bekannten Quellzeit | Antwort als erneut abgerufenen Stand behandeln; Wiederveröffentlichung zulässig, keine neue Messung behaupten | Aktuelle Antwort und Feldregeln anwenden | Kein Fehler allein wegen Wiederholung; `last_update` als Abrufzeit aktualisieren | Change Detection anwenden; nach Reconnect erneut senden |
| Quellzeit liegt vor der zuletzt akzeptierten bekannten Quellzeit | Gesamte Antwort als Rückschritt ablehnen | Bisherigen Stand behalten; keine Bereinigung | `source_time_regressed`, `last_update` unverändert | Nicht aktualisieren |
| MQTT-Verbindung oder Bestätigung eines Publishes schlägt fehl | Ausgabe gilt als unvollständig; bereits erfolgte Publishes sind nicht rückgängig gemacht | Keine weiteren Löschungen beginnen; Inventarvorgang nicht abschließen | MQTT-Fehler, soweit erreichbar; API-Abrufzeit und Zustellfehler getrennt behandeln | Fehler unabhängig erfassen; keine erfolgreiche Gesamtzustellung behaupten |

## Payload-Vertrag

Die folgenden Regeln gelten identisch für dynamische Blatt-Topics und zusätzliche
Mapping-Ziele. Nutzwerte werden als UTF-8-Text retained mit QoS 1 übertragen.
Die Payload-Spalte zeigt den tatsächlichen Text; Anführungszeichen in dieser
Spalte sind nur dann Teil der Nachricht, wenn sie ausdrücklich angezeigt sind.

| JSON-Nutzwert | MQTT-Payload | Bedeutung |
| --- | --- | --- |
| Zahl `0`, `50` oder `12.5` | `0`, `50` oder `12.5` | JSON-Zahlendarstellung ohne Einheit und ohne Anführungszeichen |
| Boolean `true` oder `false` | `true` oder `false` | Kleingeschriebener Boolean, keine Umwandlung in `1`/`0` |
| Nicht leerer String, etwa `"IDLE"` | `IDLE` | Stringinhalt ohne zusätzliche JSON-Anführungszeichen |
| Leerer String `""` | `""` | Zwei Anführungszeichen, also zwei Bytes; keine Löschung |
| Explizites `null` | `null` | Vier Bytes für einen vorhandenen unbekannten Wert; keine Löschung |
| Fehlendes Feld | Keine Nutzwert-Nachricht | Kein Ersatzwert, insbesondere weder `0` noch `null` |
| Objekt oder Array | Keine Nachricht für den Container selbst | Dynamisch werden seine skalaren Blätter publiziert; direkte Mappings auf Container erzeugen keine Ausgabe |
| Gezielte retained Bereinigung | Zero-Length-Payload, null Bytes | Separater Lösch-Publish auf einem verwalteten Topic; kein JSON-Nutzwert |

Zahlen werden ohne Rundung, Skalierung oder Einheitenumrechnung durch das Mapping
serialisiert. Die Schreibweise des ursprünglichen JSON-Texts wird nicht
garantiert: etwa `50.0` bleibt bei einem eingelesenen Float `50.0`; Exponential-
notation kann auftreten. Für den SoC sind ausschließlich endliche Werte im
Bereich 0 bis 100 zulässig. `NaN` und Unendlich sind keine gültigen JSON-Zahlen;
der allgemeine Serializer ist keine zusätzliche fachliche Wertevalidierung.

Dieses Textformat erhält nicht jeden JSON-Typ eindeutig: Der String `"null"`
und JSON-`null` ergeben beide die Payload `null`; entsprechend sind etwa
`"true"` und `true` oder `"50"` und `50` auf Payload-Ebene nicht unterscheidbar.
Auch ein String aus zwei Anführungszeichen und ein leerer String ergeben dieselbe
Payload. Verbraucher müssen den erwarteten Typ aus der Bedeutung des Quellfelds
kennen. Ein Mapping ergänzt weder Typ-Metadaten noch Konvertierungen.

Ein retained Publish mit null Bytes entfernt den bisherigen retained Wert;
die Texte `null` und `""` tun das nicht. Das folgt aus
[MQTT 3.1.1, Abschnitt 3.3.1.3](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html).
Lösch-Publishes werden getrennt von der Nutzwert-Serialisierung erzeugt und sind
erst mit der geplanten Inventarbereinigung verfügbar. Das Fehlen eines Feldes
allein löst im aktuellen Publisher noch keinen Lösch-Publish aus.

## Zeitbezug und Datenalter

`last_update` bezeichnet den erfolgreichen fachlichen Abruf, nicht den Zeitpunkt
der Fahrzeugmessung und nicht die bestätigte MQTT-Zustellung. Ein unveränderter
SoC oder Quellzeitstempel verhindert daher keine Aktualisierung der Abrufzeit.
Ein optionaler aufbereiteter `sourceTimestamp` darf nur aus einer bekannten
Quellzeit entstehen; bei fehlender Quellzeit muss sein alter verwalteter Topic
bei der Bereinigung entfallen. Fehlende Rohfelder und explizites `null` folgen
den getrennten Feldregeln der Tabelle.

Ein zeitlich weit zurückliegender Quellzeitstempel allein ist im MVP kein
Ablehnungsgrund: Es ist keine maximale Datenalter-Schwelle festgelegt. Das gilt
insbesondere beim ersten Abruf nach Prozessstart. Wiederholte oder alte Werte
dürfen nicht als neu gemessen bezeichnet werden. Ein Rückschritt lässt sich nur
gegen die zuletzt in dieser Prozesslaufzeit akzeptierte bekannte Quellzeit
erkennen. Antworten ohne Quellzeit setzen diesen Vergleichswert nicht zurück.
Eine prozessübergreifende Zeitstempel-Historie ist hier nicht vorausgesetzt.

## Grenzen und noch ausstehende Umsetzung

Bereinigt werden ausschließlich eindeutig zugeordnete dynamische und Mapping-
Topics aus dem Telemetrie-Inventar. Betriebsstatus und fremde Topics sind davon
ausgenommen. Ein HTTP-/Datenfehler erzeugt keine neue leere Sollmenge. Nach
Zustellfehlern greift die geplante Wiederaufnahme des ausstehenden Inventarvorgangs.
Eine Löschung kann wie ein normaler Publish bereits erfolgt sein, auch wenn ihre
Bestätigung verloren ging; deshalb sind Wiederholungen idempotent auszuführen.

Ein erfolgreicher Datenabruf beseitigt ausschließlich behobene Datenfehler.
Aktive Credential-, MQTT- oder openWB-Fehler dürfen dadurch nicht verschwinden;
ihre Priorisierung bleibt Aufgabe der Betriebsstatus-Implementierung.

Der aktuelle lokale Einmallauf validiert Struktur, VIN, SoC und vorhandene
Quellzeit, publiziert vorhandene skalare Werte einschließlich optionalem `null`
und wartet auf MQTT-Bestätigungen. Er vergleicht noch keine Quellzeit-Historie,
bereinigt keine retained Topics, schreibt keine Container-Statuswerte und baut
keine separate openWB-Verbindung auf. Diese Punkte bleiben in M6/M7 offen.
Der Payload-Vertrag oben beschreibt die bestehende Serialisierung; die geplanten
Lösch-Publishes sind davon ausdrücklich getrennt.
