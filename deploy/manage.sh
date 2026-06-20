#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_DIR="${HERMES_ADS_BASE_DIR:-/opt/hermes-ads}"
HERMES_ENV_FILE="${BASE_DIR}/hermes.env"
BOT_ENV_FILE="${BASE_DIR}/bot.env"
HERMES_VENV="${BASE_DIR}/venvs/hermes"
BOT_VENV="${BASE_DIR}/venvs/telegram-bot"

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  SUDO="sudo"
fi

usage() {
  cat <<EOF
Usage: deploy/manage.sh <command>

Commands:
  install       Run AlmaLinux installer
  start         Start hermes-api and telegram-bot
  stop          Stop hermes-api and telegram-bot
  restart       Restart hermes-api and telegram-bot
  status        Show service status
  logs          Follow both service logs
  logs-hermes   Follow Hermes API logs
  logs-bot      Follow Telegram bot logs
  test-hermes   Test Hermes /health and /v1/models
  update        git pull, reinstall Python deps, restart services
  env           Print env file paths
EOF
}

load_bot_env() {
  if [[ -f "${BOT_ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "${BOT_ENV_FILE}"
    set +a
  fi
}

case "${1:-help}" in
  install)
    ${SUDO} bash "${PROJECT_DIR}/deploy/install_almalinux.sh"
    ;;
  start)
    ${SUDO} systemctl start hermes-api telegram-bot
    ;;
  stop)
    ${SUDO} systemctl stop telegram-bot hermes-api
    ;;
  restart)
    ${SUDO} systemctl restart hermes-api
    sleep 5
    ${SUDO} systemctl restart telegram-bot
    ;;
  status)
    ${SUDO} systemctl --no-pager --full status hermes-api telegram-bot || true
    ;;
  logs)
    ${SUDO} journalctl -u hermes-api -u telegram-bot -f
    ;;
  logs-hermes)
    ${SUDO} journalctl -u hermes-api -f
    ;;
  logs-bot)
    ${SUDO} journalctl -u telegram-bot -f
    ;;
  test-hermes)
    load_bot_env
    : "${HERMES_API_KEY:?Missing HERMES_API_KEY in ${BOT_ENV_FILE}}"
    curl -fsS http://127.0.0.1:8642/health
    printf '\n'
    curl -fsS http://127.0.0.1:8642/v1/models \
      -H "Authorization: Bearer ${HERMES_API_KEY}"
    printf '\n'
    ;;
  update)
    git -C "${PROJECT_DIR}" pull --ff-only
    "${HERMES_VENV}/bin/python" -m pip install -e "${PROJECT_DIR}/vendor/hermes-agent"
    "${BOT_VENV}/bin/python" -m pip install -r "${PROJECT_DIR}/telegram-bot/requirements.txt"
    ${SUDO} systemctl restart hermes-api
    sleep 5
    ${SUDO} systemctl restart telegram-bot
    ;;
  env)
    printf 'Hermes env: %s\n' "${HERMES_ENV_FILE}"
    printf 'Bot env:    %s\n' "${BOT_ENV_FILE}"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
