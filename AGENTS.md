# AGENTS.md

## Ziel des Projekts
Dieses Repository betreibt einen Docker-basierten Gateway zwischen der Polestar API und MQTT. Die Data-Portal-Laufzeit liest Fahrzeugdaten über die offizielle REST-API und veröffentlicht diese an einen MQTT-Broker. Aktuell ist ein Einmallauf mit MQTT-Betriebsstatus und Offline-LWT implementiert; dauerhaftes Polling, automatischer Reconnect und separate OpenWB-Weiterleitung bleiben offene Migrationsaufgaben.

## Primäre Komponenten
- `src/polestar_mqtt/`: Data-Portal-Konfiguration, OAuth, API-Zugriffe und MQTT-Publishing
- `src/polestar_mqtt/runonce.py`: ausführbarer Einmallauf
- `api/Polestar_DataPortalAPI.json`: gebündelte OpenAPI-Spezifikation
- `docker-compose.yml` / `docker-compose_example.yml`: Container-Betrieb
- `.env` und `.env_local`: Laufzeitkonfiguration

## Laufzeit- und Konfigurationsprinzipien
- Secrets und Zugangsdaten liegen in `.env` (nicht einchecken).
- Für lokalen Start wird zusätzlich `.env_local` verwendet.
- Lokale OpenAPI- und MQTT-Mapping-Anpassungen liegen unter `local-files/`.
- Der Container mountet `./local-files` nach `/local-files`.

## Task-Tracking
- Projektaufgaben und Status werden in `TASKS.md` gepflegt: siehe [TASKS.md](TASKS.md).
- Chronologische Listen immer mit datierten Einträgen (Format: YYYY-MM-DD:) führen, neueste zuerst; bei Zeiträumen zählt das Enddatum.

## Umgang mit Git
- Vor Änderungen `git status --short` prüfen; vorhandene Änderungen und deren Staging-Zustand erhalten.
- Versionierte Dateien ausschließlich mit `git mv` verschieben oder umbenennen, niemals per `mv` oder Kopieren/Löschen. Das dabei entstehende Staging ist beabsichtigt.
- Dateien ausschließlich mit `git rm` löschen; keine direkten `rm`-Befehle und keine Umgehung durch andere Löschwerkzeuge verwenden. Nicht versionierte Dateien erhalten; keine fremden Änderungen verwerfen.
- Nur aufgabenbezogene Dateien gezielt stagen; kein pauschales `git add .` oder `git add -A`.
- Commits, Pushes und Änderungen der Git-Historie nur im ausdrücklich beauftragten Umfang durchführen. Destruktive Befehle wie `reset --hard`, `clean` oder Force-Push benötigen ausdrückliche Freigabe.
- Blockierte Git-Schreibzugriffe über die vorgesehene Berechtigungsfreigabe lösen; nicht durch Dateisystemoperationen umgehen.
- Zum Abschluss Arbeitsbaum und Index prüfen: `git diff --check`, `git diff --cached --check` und `git status --short`; Umbenennungen zusätzlich mit `git diff --cached --summary` kontrollieren.

## Arbeitsrichtlinien für Mitwirkende
- Kleine, nachvollziehbare Änderungen mit klarer Commit-Beschreibung.
- Keine Credentials, Tokens oder VINs in Code, Logs oder Commits.
- KI-Agenten führen nach jeder Code-Anpassung automatisch die fachlich passenden Tests aus und berücksichtigen das Ergebnis bei weiteren Änderungen.
- Für Python-Unit-Tests ist standardmäßig `./run_tests.sh` zu verwenden; bei Änderungen mit Einfluss auf bestehende Tests oder testbare Kernlogik soll dieser Lauf nicht ausgelassen werden.
- `./run_tests.sh` beinhaltet Linting und Tests; Lint-Fehler sind vor dem Merge zu beheben.
- Python-Linting erfolgt mit Ruff über `ruff check src tests` (keine automatische Reformatierung durch den Agent ohne explizite Anweisung).
- Ruff-Regeln werden zentral über `ruff.toml` gesteuert; Änderungen am Code-Stil orientieren sich verbindlich an dieser Konfiguration.
- Bei Lint-Fixes möglichst selektiv vorgehen (zielgerichtete Korrekturen statt großflächiger Formatierungsänderungen), um Diffs klein und reviewbar zu halten.
- Keine großflächigen Style- oder Format-Rewrites in funktionalen Änderungen, sofern nicht explizit beauftragt.
- Kommentare in `src/` und `tests/` sollen den Stil der Hauptdatei aufgreifen: knappe Abschnittsblöcke und kurze Zweckkommentare, keine redundanten Inline-Erklärungen.
- Kommentarregeln für `src/`: nur nicht offensichtliche Logik, Protokollbesonderheiten oder Fehlerpfade kommentieren; triviale Zuweisungen nicht kommentieren.
- Kommentarregeln für `tests/`: vor jedem Test-`def` eine kurze fachliche Beschreibung als Kommentar; bei komplexeren Fällen zusätzlich klare Struktur (z. B. Arrange/Act/Assert oder äquivalente Abschnittsblöcke), damit Testintention und Erwartung schnell erkennbar sind.
- Wenn Tests nicht ausgeführt werden können oder fehlschlagen, muss der KI-Agent dies transparent benennen und die Arbeit nicht als vollständig verifiziert darstellen.
- API-/Login-Änderungen mit dem passenden lokalen Modus von `./run_local.sh` prüfen; ein erfolgreicher lokaler Lauf genügt für den einzelnen Umsetzungsschritt.
- Container nur bei Docker-/Image-/Mount-spezifischen Änderungen oder ausdrücklich vorgesehenen Container-Abnahme-Gates bauen und prüfen. Kein routinemäßiger Container-Build nach jeder Codeänderung; ein entfallender Container-Test blockiert die lokale Abnahme nicht.
- Bei Änderungen an MQTT-Topics auf Rückwärtskompatibilität achten (bestehende Dashboards/Node-RED-Flows).

## Definition of Done (DoD)
- Anwendung startet ohne Fehler (lokal oder via Docker).
- Relevante automatisierte Tests wurden ausgeführt; insbesondere nach Codeänderungen mindestens `./run_tests.sh`, sofern die Änderung nicht nachweislich außerhalb des Testumfangs liegt.
- MQTT-Verbindung wird aufgebaut und LWT-Status wird publiziert.
- Polestar-Login und Datenabfrage laufen stabil über mindestens einen Zyklus.
- Doku (`README`/`doc/`) ist für geänderte Bereiche aktualisiert.
