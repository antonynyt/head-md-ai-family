#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  echo "Set GEMINI_API_KEY in the environment before running this script." >&2
  exit 1
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "Missing GEMINI_API_KEY environment variable." >&2
  echo "Export it first: export GEMINI_API_KEY=your_key" >&2
  exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Virtual environment not found at ${VENV_PYTHON}" >&2
  echo "Create it with: cd ${PROJECT_DIR} && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

cd "${PROJECT_DIR}"
exec env GEMINI_API_KEY="${GEMINI_API_KEY}" "${VENV_PYTHON}" main.py
