#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements-dev.txt"
VENV_PYTHON="${VENV_DIR}/bin/python"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_LOCAL_FILE="${SCRIPT_DIR}/.env_local"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found in PATH." >&2
    exit 1
fi

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo "Requirements file not found: ${REQUIREMENTS_FILE}" >&2
    exit 1
fi

create_venv() {
    echo "Creating virtual environment in ${VENV_DIR}"
    rm -rf "${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
}

if [[ ! -x "${VENV_PYTHON}" ]]; then
    create_venv
fi

if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "Virtual environment is incomplete. Recreating ${VENV_DIR}."
    create_venv
fi

echo "Upgrading pip tooling"
"${VENV_PYTHON}" -m pip install --quiet --upgrade pip setuptools wheel

echo "Installing Python test dependencies"
"${VENV_PYTHON}" -m pip install --quiet --upgrade -r "${REQUIREMENTS_FILE}"

echo "Running ruff lint checks"
"${VENV_PYTHON}" -m ruff check src tests

echo "Running pytest"
"${VENV_PYTHON}" -m pytest "$@"

if [[ -f "${ENV_FILE}" && -f "${ENV_LOCAL_FILE}" ]]; then
    echo "Running end-to-end check via ./run_local.sh runonce"
    "${SCRIPT_DIR}/run_local.sh" runonce
else
    echo "Skipping end-to-end check because ${ENV_FILE} and/or ${ENV_LOCAL_FILE} are missing."
fi
