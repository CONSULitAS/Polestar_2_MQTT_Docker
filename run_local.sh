#!/usr/bin/env bash
set -euo pipefail

# Resolve all paths relative to the repository root so the script works
# no matter from which directory it is started.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/src/requirements.txt"
AUTH_CHECK_MODULE="polestar_mqtt.auth_check"
DATA_PORTAL_RUNONCE_MODULE="polestar_mqtt.runonce"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_LOCAL_FILE="${SCRIPT_DIR}/.env_local"
VENV_PYTHON="${VENV_DIR}/bin/python"
APP_ARGS=("$@")

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found in PATH." >&2
    exit 1
fi

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo "Requirements file not found: ${REQUIREMENTS_FILE}" >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Create it with shared credentials for Docker and local runs." >&2
    exit 1
fi

if (( ${#APP_ARGS[@]} > 1 )); then
    echo "Usage: ./run_local.sh [runonce|auth-check|runonce-DataPortalAPI|soc-check|debug-DataPortalAPI]" >&2
    exit 1
fi

RUN_MODE="${APP_ARGS[0]:-run}"
if [[ "${RUN_MODE}" != "run" && "${RUN_MODE}" != "runonce" && "${RUN_MODE}" != "auth-check" && "${RUN_MODE}" != "soc-check" && "${RUN_MODE}" != "runonce-DataPortalAPI" && "${RUN_MODE}" != "debug-DataPortalAPI" ]]; then
    echo "Unsupported argument: ${APP_ARGS[0]}" >&2
    echo "Usage: ./run_local.sh [runonce|auth-check|runonce-DataPortalAPI|soc-check|debug-DataPortalAPI]" >&2
    exit 1
fi

if [[ "${RUN_MODE}" != "auth-check" && "${RUN_MODE}" != "soc-check" && ! -f "${ENV_LOCAL_FILE}" ]]; then
    echo "Missing ${ENV_LOCAL_FILE}. Create it with the local runtime values from docker-compose.yml." >&2
    exit 1
fi

load_env_file() {
    local file_path="$1"
    echo "Loading environment from ${file_path}"
    # Export variables from the env file automatically for the Python process.
    set -a
    # shellcheck disable=SC1090
    source "${file_path}"
    set +a
}

load_env_file "${ENV_FILE}"
if [[ -f "${ENV_LOCAL_FILE}" ]]; then
    load_env_file "${ENV_LOCAL_FILE}"
fi

create_venv() {
    echo "Creating virtual environment in ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
}

if [[ ! -x "${VENV_PYTHON}" ]]; then
    create_venv
fi

# Some systems leave behind an incomplete venv without pip support.
# In that case, repair it once before giving up.
if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "Virtual environment is incomplete. Repairing ${VENV_DIR}."
    create_venv
fi

if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "Python venv was created without pip support." >&2
    echo "On Debian/Ubuntu install the missing package first:" >&2
    echo "  sudo apt-get update && sudo apt-get install -y python3-venv" >&2
    exit 1
fi

echo "Upgrading pip tooling"
"${VENV_PYTHON}" -m pip install --quiet --upgrade pip setuptools wheel

echo "Installing Python dependencies"
"${VENV_PYTHON}" -m pip install --quiet --upgrade -r "${REQUIREMENTS_FILE}"

if [[ "${RUN_MODE}" == "debug-DataPortalAPI" ]]; then
    export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
    exec "${VENV_PYTHON}" -m polestar_mqtt.debug_responses
fi

if [[ "${RUN_MODE}" == "auth-check" ]]; then
    export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
    echo "Starting authentication-only Data Portal check"
    exec "${VENV_PYTHON}" -m "${AUTH_CHECK_MODULE}"
fi

export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export MQTT_TOPIC_MAPPING_FILE="${MQTT_TOPIC_MAPPING_FILE:-${SCRIPT_DIR}/local-files/mqtt_topic_mapping.csv}"
export MQTT_TOPIC_STATE_FILE="${MQTT_TOPIC_STATE_FILE:-${SCRIPT_DIR}/local-files/mqtt_topic_state.json}"
echo "Starting one-time Data Portal read and MQTT publication (polling is not implemented yet)"
exec "${VENV_PYTHON}" -m "${DATA_PORTAL_RUNONCE_MODULE}"
