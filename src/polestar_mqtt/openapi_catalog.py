"""Local OpenAPI loading and safe endpoint catalog construction."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from stat import S_ISREG
from urllib.parse import quote

from polestar_mqtt.config import ConfigurationError, DEFAULT_POLESTAR_OPENAPI_FILE, VIN_PATTERN


# Source checkout uses src/; the image copies its contents directly into /app.
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_BUNDLE_ROOT = _SOURCE_ROOT.parent if _SOURCE_ROOT.name == "src" else _SOURCE_ROOT
BUNDLED_OPENAPI_FILE = _BUNDLE_ROOT / "api" / "Polestar_DataPortalAPI.json"
# Authentication and vehicle discovery remain explicit client operations.
EXPLICIT_API_PATHS = frozenset({"/token", "/v1/vehicles"})
ENDPOINT_PATH_PATTERN = re.compile(
    r"/v1/vehicles/\{vin\}/(?:telemetry|charging)/"
    r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*"
)
SCOPE_PATTERN = re.compile(r"[\x21\x23-\x5B\x5D-\x7E]+")


@dataclass(frozen=True)
class Endpoint:
    """Validated operation metadata, independent of configured vehicle and broker."""

    path_template: str
    topic_root: str
    required_scopes: tuple[str, ...]
    description: str
    supported_models: tuple[str, ...] | None

    def request_path(self, vin: str) -> str:
        """Insert only a validated and URL-encoded VIN into a safe template."""

        normalized = vin.strip().upper() if isinstance(vin, str) else ""
        if not VIN_PATTERN.fullmatch(normalized):
            raise ConfigurationError("POLESTAR_VIN must be a valid 17-character VIN")
        if not ENDPOINT_PATH_PATTERN.fullmatch(self.path_template):
            raise ConfigurationError("OpenAPI endpoint template is invalid")
        return self.path_template.replace("{vin}", quote(normalized, safe=""))


def _operation_metadata(path: str, operation: dict) -> Endpoint:
    scopes = operation.get("x-required-scopes")
    if not isinstance(scopes, list) or not scopes or any(
        not isinstance(scope, str) or not SCOPE_PATTERN.fullmatch(scope) for scope in scopes
    ):
        raise ConfigurationError("OpenAPI x-required-scopes must contain valid scope strings")
    models = operation.get("x-supported-models")
    if "x-supported-models" in operation and (
        not isinstance(models, list) or any(
            not isinstance(model, str) or not model.strip() for model in models
        )
    ):
        raise ConfigurationError("OpenAPI x-supported-models must contain model names")
    for key in ("description", "summary"):
        if key in operation and not isinstance(operation[key], str):
            raise ConfigurationError("OpenAPI description and summary must be strings")
    description = operation.get("description") or operation.get("summary", "")
    return Endpoint(
        path_template=path,
        topic_root=path.removeprefix("/v1/vehicles/{vin}"),
        required_scopes=tuple(scopes),
        description=description,
        supported_models=tuple(models) if models is not None else None,
    )


def select_openapi_file(
    local_file: Path = DEFAULT_POLESTAR_OPENAPI_FILE,
    *,
    bundled_file: Path = BUNDLED_OPENAPI_FILE,
) -> Path:
    """Prefer a local regular file; fall back only when that path is absent."""

    for candidate in (local_file, bundled_file):
        try:
            metadata = candidate.stat()
        except FileNotFoundError:
            if candidate.is_symlink():
                raise ConfigurationError("OpenAPI file is a dangling symbolic link") from None
            continue
        except (OSError, ValueError):
            raise ConfigurationError("OpenAPI file cannot be accessed") from None
        if not S_ISREG(metadata.st_mode):
            raise ConfigurationError("OpenAPI source must be a regular file")
        return candidate
    raise ConfigurationError("No local or bundled OpenAPI file is available")


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-standard JSON constant")


def load_openapi_document(
    local_file: Path = DEFAULT_POLESTAR_OPENAPI_FILE,
    *,
    bundled_file: Path = BUNDLED_OPENAPI_FILE,
) -> dict:
    """Read one startup snapshot and validate the supported document structure."""

    selected = select_openapi_file(local_file, bundled_file=bundled_file)
    try:
        document = json.loads(
            selected.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_constant,
        )
    except (OSError, ValueError, RecursionError):
        raise ConfigurationError("OpenAPI file cannot be read as valid UTF-8 JSON") from None

    if not isinstance(document, dict):
        raise ConfigurationError("OpenAPI document must be an object")
    version = document.get("openapi")
    if not isinstance(version, str) or not re.fullmatch(r"3\.1\.[0-9]+", version):
        raise ConfigurationError("OpenAPI version must be 3.1.x")
    info = document.get("info")
    if not isinstance(info, dict) or any(
        not isinstance(info.get(key), str) or not info[key].strip()
        for key in ("title", "version")
    ):
        raise ConfigurationError("OpenAPI info requires title and version")
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ConfigurationError("OpenAPI paths must be a non-empty object")
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    for path, item in paths.items():
        if path.startswith("x-"):
            continue
        if not path.startswith("/") or not isinstance(item, dict):
            raise ConfigurationError("OpenAPI path entries must be objects with absolute paths")
        for method in methods & item.keys():
            operation = item[method]
            if not isinstance(operation, dict):
                raise ConfigurationError("OpenAPI operations must be objects")
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                raise ConfigurationError("OpenAPI operations require response objects")
            if any(not isinstance(response, dict) for response in responses.values()):
                raise ConfigurationError("OpenAPI response entries must be objects")
    if "components" in document and not isinstance(document["components"], dict):
        raise ConfigurationError("OpenAPI components must be an object")
    return document


def build_endpoint_catalog(document: dict) -> tuple[Endpoint, ...]:
    """Return sorted GET metadata from an already loaded OpenAPI document."""

    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ConfigurationError("OpenAPI paths must be an object")
    endpoints = []
    for path, item in paths.items():
        if not isinstance(path, str):
            raise ConfigurationError("OpenAPI path must be a string")
        if path.startswith("x-") or path in EXPLICIT_API_PATHS:
            continue
        if not ENDPOINT_PATH_PATTERN.fullmatch(path):
            raise ConfigurationError("OpenAPI path is outside the supported vehicle endpoints")
        if not isinstance(item, dict) or "$ref" in item:
            raise ConfigurationError("OpenAPI catalog requires inline path objects")
        if "get" not in item:
            continue
        operation = item["get"]
        if not isinstance(operation, dict) or "$ref" in operation:
            raise ConfigurationError("OpenAPI catalog requires inline GET operations")
        endpoints.append(_operation_metadata(path, operation))
    return tuple(sorted(endpoints, key=lambda endpoint: endpoint.path_template))


def aggregate_scopes(endpoints: tuple[Endpoint, ...]) -> str:
    """Build a deterministic token scope from the complete endpoint catalog."""

    scopes = {scope for endpoint in endpoints for scope in endpoint.required_scopes}
    if not scopes:
        raise ConfigurationError("OpenAPI endpoint catalog requires at least one scope")
    return " ".join(sorted(scopes))
