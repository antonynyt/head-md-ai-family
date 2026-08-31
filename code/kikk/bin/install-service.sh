#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_SRC="${PROJECT_DIR}/kikk.service"
SERVICE_DEST="/etc/systemd/system/kikk.service"
ENV_FILE="/home/kiki/.config/familect.env"

if [[ ! -f "${SERVICE_SRC}" ]]; then
  echo "Service file not found: ${SERVICE_SRC}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file not found: ${ENV_FILE}" >&2
  echo "Create it first with:" >&2
  echo "  sudo mkdir -p /home/kiki/.config" >&2
  echo "  sudo tee /home/kiki/.config/familect.env >/dev/null <<'EOF'" >&2
  echo "  GEMINI_API_KEY=YOUR_KEY_HERE" >&2
  echo "  EOF" >&2
  echo "  sudo chown kiki:kiki /home/kiki/.config/familect.env" >&2
  echo "  sudo chmod 600 /home/kiki/.config/familect.env" >&2
  exit 1
fi

sudo cp "${SERVICE_SRC}" "${SERVICE_DEST}"
sudo systemctl daemon-reload
sudo systemctl enable kikk.service
sudo systemctl restart kikk.service
sudo systemctl status kikk.service --no-pager -l
