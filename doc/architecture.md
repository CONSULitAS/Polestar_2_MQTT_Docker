# Architektur

## Überblick
Das Projekt verbindet die Polestar-Cloud-API mit einem lokalen MQTT-Broker.

## Komponenten
- Offizielle Polestar Data Portal M2M API (`pc-api.polestar.com`)
- Legacy-Laufzeit während der Migration (`src/Polestar_2_MQTT.py`, `src/auth.py`,
  `src/graphql_queries.py`)
- Neue Data-Portal-Laufzeit (`src/polestar_mqtt/`)
- MQTT-Broker (z. B. Mosquitto)
- Optional: OpenWB v1 MQTT-Endpoint

## Datenfluss
1. Dienst liest ENV-Konfiguration.
2. Während der Migration: Login gegen Polestar ID und GraphQL-Aufrufe über den
   bestehenden Einstiegspunkt.
3. Zielzustand: Die gebündelte oder lokal aktualisierte OpenAPI-Datei wird beim
   Containerstart einmal validiert. Ausschließlich erlaubte Fahrzeug-GET-Pfade
   bilden zusammen mit ihren Scopes den Endpoint-Katalog; die konfigurierte
   API-Basis bleibt unabhängig von `servers` in der Datei maßgeblich. Änderungen
   der Datei werden erst nach einem Container-Neustart übernommen.
4. OAuth2 Client Credentials fordern ein Token mit den aggregierten Scopes der
   katalogisierten Endpunkte an; `/v1/vehicles` validiert die konfigurierte VIN.
5. Der Client arbeitet den Endpoint-Katalog sequenziell ab. Fehler bleiben auf
   den jeweiligen Endpunkt begrenzt.
6. Erfolgreiche JSON-Antworten werden unter einer vom API-Pfad abgeleiteten
   MQTT-Wurzel dynamisch publiziert. Optionale CSV-Mappings ergänzen weitere
   Ziel-Topics, ohne den dynamischen Baum zu ersetzen.
7. Der Battery-SoC erhält zusätzliche Fachvalidierung und kann optional an
   OpenWB weitergeleitet werden.

## Erweiterungspunkte
- Anpassbare GraphQL-Queries über `local-files/graphql_queries.py`
- Aktualisierbare OpenAPI-Spezifikation über
  `local-files/Polestar_DataPortalAPI.json` mit gebündeltem Fallback unter `api/`
- Zusätzliche lokale MQTT-Ziele über `local-files/mqtt_topic_mapping.csv`
- ENV-gesteuerte MQTT-/OpenWB-Parameter via Docker Compose

## Grenzen der OpenAPI-Steuerung
- Alle erlaubten GET-Endpunkte des Katalogs werden berücksichtigt, einschließlich
  Location. Es gibt keine konfigurierbare Endpunktauswahl; Modellhinweise
  deaktivieren keine Endpunkte. Antwortet die API mit einer Fehlermeldung passend
  zu `No .* data is available for this vehicle`, wird der betroffene Fahrzeugpfad
  im Speicher des laufenden API-Clients ausgeschlossen. Weitere Abrufe und Retries
  dieses Pfads entfallen; ein neuer Prozess startet mit leerer Ausschlussliste.
  Der spätere Polling-Ablauf muss dieselbe Client-Instanz über seine Zyklen halten.
- Jeder HTTP-Fehlerbody wird ausgewertet und als `httpstatus / code: message`
  auf der Konsole protokolliert, auch vor Token-Erneuerung oder temporären Retries.
  Der tatsächliche HTTP-Status ist maßgeblich. Ungültige Bodies erhalten
  `HTTP_ERROR: No valid API error message`; VINs und bekannte Zugangsdaten werden
  redigiert. Bereits ausgeschlossene Pfade verursachen keine neue HTTP-Meldung.
- `POLESTAR_API_BASE_URL` wird in Konfiguration und HTTP-Client als HTTPS-URL
  mit Host und gültigem optionalem Port geprüft. Eingebettete Zugangsdaten,
  Query, Fragment, Whitespace und Backslashes sind unzulässig; Fehlermeldungen
  enthalten den konfigurierten Wert nicht. Abschließende Slashes werden entfernt.
  OpenAPI-`servers` auf Dokument-, Pfad- und Operationsebene werden nicht zur
  Zielauswahl herangezogen. Nur die konfigurierte Basis bestimmt die Request-URL.
- `build_endpoint_catalog()` bildet beim Start des Data-Portal-Einmallaufs einen
  sortierten, unveränderlichen Katalog aus GET-Pfadtemplates unter
  `/v1/vehicles/{vin}/telemetry/` und `/v1/vehicles/{vin}/charging/`.
  Nach dem Präfix sind ausschließlich nicht leere Segmente aus ASCII-Buchstaben,
  Ziffern, Bindestrichen und Unterstrichen erlaubt. Weitere Platzhalter,
  Prozentkodierung, Punktsegmente, Query, Fragment und Backslashes werden
  abgelehnt. Pfad-/Operationsreferenzen werden nicht aufgelöst und sind unzulässig.
  `/token`, `/v1/vehicles` und `x-`-Metadaten bleiben außerhalb des Katalogs;
  Schreiboperationen werden ausgeschlossen, unbekannte Pfade abgelehnt.
  Der Katalog liefert die Scopes für den Token-Abruf und wird im
  Data-Portal-Einmallauf sequenziell über `get_catalog()` abgearbeitet.
- `get_endpoint()` ruft jedes Pfadtemplate über den bestehenden autorisierten
  GET-Transport ab (Timeouts, Token-Erneuerung und Retry unverändert) und verlangt
  eine JSON-Objektantwort. `get_catalog()` hält Antworten nach Pfadtemplate vor.
  API-/Antwort-/Tokenfehler werden getrennt nach Pfadtemplate mit ihrem sicheren
  Exception-Typ erfasst; erfolgreiche Antworten bleiben verfügbar. Ein fehlerhafter
  Endpunkt blockiert weder nachfolgende Abrufe noch eine gültige Battery-Ausgabe.
  MQTT erhält alle erfolgreichen Antworten unter `<base>` plus `topic_root`,
  einschließlich `data` und `meta`. Battery wird zusätzlich auf SoC, VIN und
  Zeitstempel geprüft; bei Fehlern werden nur ihre Ausgabe und ihr Mapping
  ausgelassen. Der dauerhafte Polling-Ablauf bleibt M7 vorbehalten.
- Der Einmallauf meldet bei bestätigter Veröffentlichung und Fehlern anderer
  Endpunkte `data_portal: partial` und `failed_endpoints`, Exit-Code 0. Sind keine
  publizierbaren Daten vorhanden, endet er vor MQTT mit Exit-Code 1; das bisherige
  Topic-Inventar bleibt unverändert. Retained-Bereinigung erfolgt weiterhin nicht.
  Das Inventar enthält nach vollständig bestätigter Veröffentlichung die Topics
  dieses Durchlaufs; eine endpunktbezogene Inventarfortschreibung bleibt M6.2.
- Alle dynamischen Topic-Namen und Kollisionen zwischen Endpunkten sowie mit
  Mapping-Zielen werden vor der MQTT-Verbindung geprüft. Die bestehende CSV mit
  Quellen wie `data.batteryChargeLevelPercentage` bezieht sich weiterhin auf
  Battery; sie wird nicht mehrfach auf andere Endpunktantworten angewendet.
- Katalogeinträge sind unveränderliche `Endpoint`-Objekte mit `path_template`,
  `topic_root` (z. B. `/telemetry/battery`), `required_scopes`, `description`
  und optionalen `supported_models`. Die Topic-Wurzel enthält weder MQTT-Basis
  noch VIN. `x-required-scopes` muss eine nicht leere Liste gültiger einzelner
  Scope-Zeichenfolgen sein. Beschreibungen nutzen
  bei fehlender oder leerer `description` die `summary`, sonst einen leeren Text.
  Fehlende Modellhinweise werden als `None` erfasst; vorhandene Listen dürfen
  nur nicht leere Namen enthalten und dienen ausschließlich als Hinweis.
  `request_path(vin)` normalisiert und prüft die VIN mit der bestehenden
  VIN-Regel und setzt sie URL-kodiert in das erneut geprüfte Template ein.
- `aggregate_scopes()` sammelt alle Scopes des vollständigen Katalogs,
  dedupliziert und sortiert sie und verbindet sie mit Leerzeichen. Ein leerer
  Scope-Satz wird abgelehnt. Der Data-Portal-Einmallauf übergibt den String an
  den `TokenProvider`; dieser verwendet ihn auch bei Ablauf und nach `401`
  unverändert. Die getrennten Auth-only-/SoC-Diagnosen behalten den Battery-Scope.
- Die versionierte Spezifikation liegt unter `api/Polestar_DataPortalAPI.json`
  und wird beim Image-Build nach `/app/api/Polestar_DataPortalAPI.json` kopiert.
  `select_openapi_file()` in `openapi_catalog.py` wählt die über
  `POLESTAR_OPENAPI_FILE` konfigurierte lokale Datei (Standard:
  `/local-files/Polestar_DataPortalAPI.json`), andernfalls den gebündelten Fallback.
  Relative lokale Pfade beziehen sich auf das Arbeitsverzeichnis; der gebündelte
  Pfad ist davon unabhängig. Eine leere ENV-Angabe verwendet den Standardpfad.
  Nur eine fehlende lokale Datei erlaubt den Fallback; Verzeichnisse, defekte
  Symlinks und Fehler beim Dateistatus-Zugriff werden ohne Pfadausgabe abgelehnt.
  Die Auswahl selbst lädt keine Inhalte und führt keine Downloads aus.
- `load_openapi_document()` liest die gewählte Datei als UTF-8-JSON (BOM erlaubt)
  und prüft OpenAPI `3.1.x`, `info.title`, `info.version`, nicht leere `paths`,
  Pfad-/Operations-/Antwortobjekte sowie den Objekttyp optionaler `components`.
  Doppelte JSON-Schlüssel und nicht standardkonforme Konstanten wie `NaN`
  werden abgelehnt. Eine ungültige lokale Datei löst keinen Fallback aus.
  Dies ist eine Grundstrukturprüfung, keine vollständige OpenAPI-Schemavalidierung.
- Der Data-Portal-Einmallauf lädt beim Start einmal vor HTTP und MQTT; ungültige
  Dateien führen zu Exit-Code 2 ohne Ausgabe von Dateiinhalten oder Pfaden.
  Der geladene Snapshot wird nicht automatisch aktualisiert; eine neue Datei
  wirkt erst beim nächsten Prozessstart. Auth-only- und SoC-Diagnose bleiben
  unabhängig. Der dauerhafte Start-/Polling-Ablauf und die Umstellung des
  Legacy-Container-Einstiegspunkts bleiben M7/M8 vorbehalten.
- Automatisch übernommen werden nur kompatible `GET`-Operationen unter den
  freigegebenen Telemetrie- und Charging-Pfaden.
- Token- und Fahrzeuglistenabruf sowie VIN-, SoC- und Sicherheitsvalidierung
  bleiben explizite Programmlogik.
- Änderungen an Authentifizierung, HTTP-Methoden oder inkompatiblen
  Antwortverträgen erfordern weiterhin Codeänderungen.
- Eine lokale Spezifikation wird nicht automatisch aus dem Internet geladen und
  darf weder die Basis-URL noch beliebige neue Request-Ziele einschleusen.

## Migrationsgrenze
- Upstream-Änderungen am bisherigen Login bleiben in `src/auth.py` erhalten.
- Die offizielle API wird getrennt im Package `src/polestar_mqtt/` implementiert.
- Beide Testbereiche werden über die zentrale Root-Konfiguration `pytest.ini` ausgeführt.
- Erst nach erfolgreichem Container-QS-Check wird der Docker-Einstiegspunkt umgestellt.

## Bekannte technische Schwerpunkte
- Reconnect-Verhalten bei MQTT-Ausfällen
- Fehlerbehandlung im Auth-/Redirect-Flow
- Konfigurierbarkeit des OpenWB-Topics
