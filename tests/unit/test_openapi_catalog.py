"""Tests for local OpenAPI selection and bundled fallback."""

from pathlib import Path

import pytest

from polestar_mqtt.config import ConfigurationError
from polestar_mqtt.openapi_catalog import BUNDLED_OPENAPI_FILE, select_openapi_file


# Eine vorhandene lokale OpenAPI-Datei hat bei der Dateiauswahl Vorrang vor dem Bundle.
def test_local_file_takes_precedence_without_parsing(tmp_path):
    local = tmp_path / "local.json"
    local.write_text("validation belongs to the loader", encoding="utf-8")

    assert select_openapi_file(local, bundled_file=tmp_path / "missing.json") == local


# Ohne lokale Datei wird das Bundle unabhängig vom Arbeitsverzeichnis gefunden.
def test_missing_local_uses_bundle_independently_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert select_openapi_file(tmp_path / "missing.json") == BUNDLED_OPENAPI_FILE
    assert BUNDLED_OPENAPI_FILE.is_file()


# Fehlen lokale Datei und Bundle, nennt die Fehlermeldung keine vertraulichen Pfade.
def test_missing_sources_are_reported_without_paths(tmp_path):
    with pytest.raises(ConfigurationError, match="No local or bundled") as error:
        select_openapi_file(tmp_path / "private-local", bundled_file=tmp_path / "private-bundle")

    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize("invalid_source", ["local", "bundle"])
# Verzeichnisse werden weder lokal noch im Bundle als OpenAPI-Dateien akzeptiert.
def test_directory_is_not_a_source(tmp_path, invalid_source):
    local = tmp_path if invalid_source == "local" else tmp_path / "missing"
    with pytest.raises(ConfigurationError, match="regular file"):
        select_openapi_file(local, bundled_file=tmp_path)


# Ein defekter lokaler Symlink darf nicht stillschweigend durch das Bundle ersetzt werden.
def test_broken_local_symlink_does_not_silently_fall_back(tmp_path):
    local = tmp_path / "local.json"
    local.symlink_to(tmp_path / "missing")

    with pytest.raises(ConfigurationError, match="dangling symbolic link"):
        select_openapi_file(local)


# Ein Zugriffsfehler stoppt die Dateiauswahl ohne Fallback oder Pfadausgabe.
def test_access_error_does_not_silently_fall_back_or_expose_path(tmp_path, monkeypatch):
    def denied(path):
        raise PermissionError("private-path")

    monkeypatch.setattr(Path, "stat", denied)
    with pytest.raises(ConfigurationError, match="cannot be accessed") as error:
        select_openapi_file(tmp_path / "local.json")

    assert "private-path" not in str(error.value)
    assert error.value.__suppress_context__


# Ein geladener OpenAPI-Stand bleibt trotz späterer Dateiänderung unverändert.
def test_loader_reads_bundle_and_keeps_snapshot(tmp_path):
    import json
    from polestar_mqtt.openapi_catalog import load_openapi_document

    document = load_openapi_document(tmp_path / "missing")
    local = tmp_path / "local.json"
    local.write_text(json.dumps(document), encoding="utf-8")
    snapshot = load_openapi_document(local)
    local.write_text("invalid", encoding="utf-8")
    assert snapshot == document
    with pytest.raises(ConfigurationError):
        load_openapi_document(local)


@pytest.mark.parametrize("content", [
    b"{", b"\xff", b"[]", b'{"openapi":"3.1.0","openapi":"3.1.1"}',
    b'{"value":NaN}', b'{"value":Infinity}',
])
# Ungültiges lokales JSON wird abgelehnt, statt auf das Bundle zurückzufallen.
def test_loader_rejects_invalid_json_without_fallback(tmp_path, content):
    from polestar_mqtt.openapi_catalog import load_openapi_document

    local = tmp_path / "private-path"
    local.write_bytes(content)
    with pytest.raises(ConfigurationError) as error:
        load_openapi_document(local)
    assert "private-path" not in str(error.value)


@pytest.mark.parametrize("changes", [
    {"openapi": "3.0.3"}, {"openapi": "4.0.0"}, {"openapi": 3.1},
    {"info": {}}, {"info": []}, {"paths": {}}, {"paths": []},
    {"paths": {"relative": {}}}, {"paths": {"/test": []}},
    {"paths": {"/test": {"get": []}}},
    {"paths": {"/test": {"get": {"responses": {}}}}},
    {"paths": {"/test": {"get": {"responses": {"200": []}}}}},
    {"components": []},
])
# Nicht unterstützte OpenAPI-Versionen und fehlerhafte Grundstrukturen werden abgelehnt.
def test_loader_rejects_invalid_structures(tmp_path, changes):
    import json
    from polestar_mqtt.openapi_catalog import load_openapi_document

    document = load_openapi_document(tmp_path / "missing")
    document.update(changes)
    local = tmp_path / "local.json"
    local.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_openapi_document(local)


# Lesefehler der OpenAPI-Datei werden ohne vertrauliche Pfadangaben gemeldet.
def test_loader_redacts_read_errors(tmp_path, monkeypatch):
    from polestar_mqtt.openapi_catalog import load_openapi_document

    def denied(*args, **kwargs):
        raise PermissionError("private-path")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(ConfigurationError, match="valid UTF-8 JSON") as error:
        load_openapi_document(tmp_path / "missing")
    assert "private-path" not in str(error.value)
    assert error.value.__suppress_context__


# Neue erlaubte GETs werden katalogisiert; Login, Fahrzeugliste und Schreibzugriffe nicht.
def test_catalog_accepts_new_get_and_excludes_explicit_and_write_operations():
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog

    charging = "/v1/vehicles/{vin}/charging/new-setting"
    telemetry = "/v1/vehicles/{vin}/telemetry/new_field/details"
    document = {"paths": {
        telemetry: {"get": {"x-required-scopes": ["test/read"]}, "post": {}},
        "/token": {"post": {}},
        "/v1/vehicles": {"get": {}},
        charging: {"get": {"x-required-scopes": ["test/read"]}},
        "/v1/vehicles/{vin}/charging/writeOnly": {"put": {}, "delete": {}},
        "x-extension": "metadata",
    }}
    assert tuple(entry.path_template for entry in build_endpoint_catalog(document)) == (
        charging, telemetry,
    )


@pytest.mark.parametrize("path", [
    "/v1/unknown", "https://example.invalid/telemetry/battery",
    "//example.invalid/v1/vehicles/{vin}/telemetry/battery",
    "/v1/vehicles/{vin}/telemetry/../battery",
    "/v1/vehicles/{vin}/telemetry/%2e%2e/battery",
    "/v1/vehicles/{vin}/telemetry/%252e%252e/battery",
    "/v1/vehicles/{vin}/telemetry/battery?target=other",
    "/v1/vehicles/{vin}/telemetry/battery#fragment",
    "/v1/vehicles/{vin}/telemetry/battery\\other",
    "/v1/vehicles/{vin}/telemetry/{other}",
    "/v1/vehicles/{vin}/telemetry//battery",
    "/v1/vehicles/{vin}/telemetry/", "/v1/vehicles/{vin}/telemetry/battery/",
    "/v1/vehicles/{vin}/telemetry/battery\n",
    "/v1/vehicles/other/telemetry/battery",
    "/v1/vehicles/{vin}/commands/start",
])
# Unbekannte oder unsichere Endpunktpfade werden ohne Wiedergabe des Pfads abgelehnt.
def test_catalog_rejects_unknown_or_unsafe_paths_without_echoing_them(path):
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog

    with pytest.raises(ConfigurationError) as error:
        build_endpoint_catalog({"paths": {path: {"get": {}}}})
    assert path not in str(error.value)


@pytest.mark.parametrize("item", [
    {"$ref": "https://example.invalid/paths.json"},
    {"get": {"$ref": "#/other"}}, {"get": None}, [],
])
# Referenzierte oder fehlerhafte Operationen dürfen keine Katalogeinträge erzeugen.
def test_catalog_rejects_indirect_or_invalid_operations(item):
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog

    with pytest.raises(ConfigurationError):
        build_endpoint_catalog({"paths": {"/v1/vehicles/{vin}/telemetry/battery": item}})


# Das Bundle liefert genau die 15 fachlichen Fahrzeug-GETs ohne Login und Fahrzeugliste.
def test_bundled_catalog_contains_only_fifteen_vehicle_gets(tmp_path):
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog, load_openapi_document

    catalog = build_endpoint_catalog(load_openapi_document(tmp_path / "missing"))
    assert len(catalog) == 15
    paths = [entry.path_template for entry in catalog]
    assert "/v1/vehicles/{vin}/telemetry/battery" in paths
    assert "/token" not in paths
    assert "/v1/vehicles" not in paths


def make_endpoint(**metadata):
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog

    operation = {"x-required-scopes": ["test/read"], **metadata}
    return build_endpoint_catalog({"paths": {
        "/v1/vehicles/{vin}/telemetry/new-field": {"get": operation},
    }})[0]


# Katalogmetadaten bleiben unveränderlich und unabhängig vom ursprünglichen JSON.
def test_metadata_is_copied_into_immutable_entry():
    from dataclasses import FrozenInstanceError

    scopes = ["test/read", "test/extra"]
    models = ["Polestar 2"]
    entry = make_endpoint(**{
        "x-required-scopes": scopes, "x-supported-models": models,
        "description": "Detailed description", "summary": "Short summary",
    })
    scopes.clear()
    models.clear()
    assert entry.topic_root == "/telemetry/new-field"
    assert entry.required_scopes == ("test/read", "test/extra")
    assert entry.supported_models == ("Polestar 2",)
    assert entry.description == "Detailed description"
    with pytest.raises(FrozenInstanceError):
        entry.description = "changed"


# Fehlende Modellhinweise sind zulässig; die Kurzbeschreibung ersetzt fehlende Langtexte.
def test_optional_metadata_and_summary_fallback():
    assert make_endpoint().description == ""
    assert make_endpoint().supported_models is None
    assert make_endpoint(summary="Short summary").description == "Short summary"


@pytest.mark.parametrize("metadata", [
    {"x-required-scopes": None}, {"x-required-scopes": []},
    {"x-required-scopes": "test/read"}, {"x-required-scopes": [False]},
    {"x-required-scopes": ["test/read test/write"]},
    {"x-required-scopes": ["test/read\n"]}, {"x-required-scopes": ["test/é"]},
    {"x-supported-models": None}, {"x-supported-models": "Polestar 2"},
    {"x-supported-models": [""]}, {"x-supported-models": [2]},
    {"description": None}, {"summary": []},
])
# Fehlerhafte Scopes, Modellhinweise und Beschreibungen verhindern die Katalogbildung.
def test_invalid_metadata_is_rejected(metadata):
    with pytest.raises(ConfigurationError):
        make_endpoint(**metadata)


# Ein fachlicher GET ohne erforderliche Scope-Angabe wird nicht katalogisiert.
def test_missing_required_scopes_is_rejected():
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog

    with pytest.raises(ConfigurationError, match="x-required-scopes"):
        build_endpoint_catalog({"paths": {
            "/v1/vehicles/{vin}/charging/new-field": {"get": {}},
        }})


# Eine gültige VIN wird normalisiert in das freigegebene Pfadtemplate eingesetzt.
def test_request_path_normalizes_valid_vin():
    entry = make_endpoint()
    assert entry.request_path(" lpsvs000000000000 ") == (
        "/v1/vehicles/LPSVS000000000000/telemetry/new-field"
    )


@pytest.mark.parametrize("vin", [
    None, "", "../outside", "LPSVS00000000000I", "LPSVS000000000000/extra",
    "LPSVS000000000000?x=y", "LPSVS000000000000%2f", "LPSVS000000000000\nother",
])
# Ungültige VINs dürfen weder einen Request-Pfad bilden noch im Fehlertext erscheinen.
def test_request_path_rejects_invalid_vin_without_echoing_it(vin):
    with pytest.raises(ConfigurationError) as error:
        make_endpoint().request_path(vin)
    if vin:
        assert vin not in str(error.value)


# Auch manuell erzeugte Einträge dürfen die erlaubten Request-Pfade nicht umgehen.
def test_request_path_rechecks_manually_constructed_template():
    from dataclasses import replace

    entry = replace(make_endpoint(), path_template="https://untrusted.invalid/{vin}")
    with pytest.raises(ConfigurationError, match="template"):
        entry.request_path("LPSVS000000000000")


# Das Bundle liefert Scopes, Kurzbeschreibung und Modellhinweise ohne Modellfilterung.
def test_bundled_metadata_uses_summary_and_preserves_model_hints(tmp_path):
    from polestar_mqtt.openapi_catalog import build_endpoint_catalog, load_openapi_document

    catalog = build_endpoint_catalog(load_openapi_document(tmp_path / "missing"))
    entry = next(e for e in catalog if e.topic_root == "/charging/charge-locations")
    assert entry.required_scopes == ("pdp-charging/chargeLocations",)
    assert entry.supported_models == ("Polestar 3",)
    assert entry.description


# Katalog-Scopes werden eindeutig sortiert und stammen nur aus den übergebenen Einträgen.
def test_scope_aggregation_is_sorted_unique_and_uses_only_given_endpoints():
    from polestar_mqtt.openapi_catalog import aggregate_scopes

    first = make_endpoint(**{"x-required-scopes": ["test/z", "test/a", "test/z"]})
    second = make_endpoint(**{"x-required-scopes": ["test/a", "test/b"]})
    assert aggregate_scopes((first, second)) == "test/a test/b test/z"
    assert aggregate_scopes((second, first)) == "test/a test/b test/z"
    assert aggregate_scopes((second,)) == "test/a test/b"


# Ein leerer Katalog darf keinen Tokenabruf mit ungewollten Standard-Scopes auslösen.
def test_empty_catalog_does_not_request_implicit_default_scopes():
    from polestar_mqtt.openapi_catalog import aggregate_scopes

    with pytest.raises(ConfigurationError, match="at least one scope"):
        aggregate_scopes(())
