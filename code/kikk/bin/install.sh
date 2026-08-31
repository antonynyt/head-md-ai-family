#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
REQUIREMENTS_FILE="${PROJECT_DIR}/requirements.txt"
VENV_PYTHON="${VENV_DIR}/bin/python"

if [[ -d "${VENV_DIR}" ]]; then
  if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "Existing virtual environment is broken; recreating it."
    rm -rf "${VENV_DIR}"
  fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating Python virtual environment in ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${REQUIREMENTS_FILE}"

echo "Virtual environment ready at ${VENV_DIR}"
