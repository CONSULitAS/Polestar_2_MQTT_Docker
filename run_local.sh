#!/usr/bin/env bash
set -euo pipefail

# Resolve all paths relative to the repository root so the script works
# no matter from which directory it is started.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/src/requirements.txt"
APP_FILE="${SCRIPT_DIR}/src/Polestar_2_MQTT.py"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_LOCAL_FILE="${SCRIPT_DIR}/.env_local"
VENV_PYTHON="${VENV_DIR}/bin/python"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found in PATH." >&2
    exit 1
fi

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo "Requirements file not found: ${REQUIREMENTS_FILE}" >&2
    exit 1
fi

if [[ ! -f "${APP_FILE}" ]]; then
    echo "Application file not found: ${APP_FILE}" >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Create it with shared credentials for Docker and local runs." >&2
    exit 1
fi

if [[ ! -f "${ENV_LOCAL_FILE}" ]]; then
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
load_env_file "${ENV_LOCAL_FILE}"

create_venv() {
    echo "Creating virtual environment in ${VENV_DIR}"
    # Recreate from scratch so a half-created venv cannot survive unnoticed.
    rm -rf "${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
}

if [[ ! -x "${VENV_PYTHON}" ]]; then
    create_venv
fi

# Some systems leave behind an incomplete venv without pip support.
# In that case, rebuild it once before giving up.
if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "Virtual environment is incomplete. Recreating ${VENV_DIR}."
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

# These variables must be set and non-empty for a local run.
missing_env=()
for var_name in     POLESTAR_EMAIL     POLESTAR_PASSWORD     POLESTAR_VIN     TZ     POLESTAR_CYCLE     MQTT_BROKER     MQTT_PORT     MQTT_BASE_TOPIC     OPENWB_HOST     OPENWB_PUBLISH     OPENWB_PORT     OPENWB_LP_NUM; do
    if [[ -z "${!var_name:-}" ]]; then
        missing_env+=("${var_name}")
    fi
done

# Empty MQTT credentials are valid, but the variables should still exist.
missing_optional_env=()
for var_name in MQTT_USER MQTT_PASSWORD; do
    if [[ -z "${!var_name+x}" ]]; then
        missing_optional_env+=("${var_name}")
    fi
done

if (( ${#missing_env[@]} > 0 )); then
    echo "Missing required environment variables: ${missing_env[*]}" >&2
    echo "Check ${ENV_FILE} and ${ENV_LOCAL_FILE}." >&2
    exit 1
fi

if (( ${#missing_optional_env[@]} > 0 )); then
    echo "Missing optional environment variables: ${missing_optional_env[*]}" >&2
    echo "Define them in ${ENV_FILE}, even if they are intentionally empty." >&2
    exit 1
fi

echo "Starting ${APP_FILE}"
exec "${VENV_PYTHON}" -u "${APP_FILE}"
