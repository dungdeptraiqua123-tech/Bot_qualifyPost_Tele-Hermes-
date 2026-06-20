#!/usr/bin/env bash
set -Eeuo pipefail

BASE_DIR="${HERMES_ADS_BASE_DIR:-/opt/hermes-ads}"
RUN_USER="${HERMES_ADS_USER:-hermesads}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HERMES_HOME="${BASE_DIR}/hermes-home"
HERMES_ENV_FILE="${BASE_DIR}/hermes.env"
BOT_ENV_FILE="${BASE_DIR}/bot.env"
HERMES_VENV="${BASE_DIR}/venvs/hermes"
BOT_VENV="${BASE_DIR}/venvs/telegram-bot"
HERMES_SERVICE="/etc/systemd/system/hermes-api.service"
BOT_SERVICE="/etc/systemd/system/telegram-bot.service"

NO_PROMPT=0
if [[ "${1:-}" == "--no-prompt" ]]; then
  NO_PROMPT=1
fi

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run as root: bash deploy/install_almalinux.sh"
  fi
}

ensure_project_layout() {
  [[ -f "${PROJECT_DIR}/telegram-bot/app/main.py" ]] || die "Missing telegram-bot/app/main.py"
  [[ -f "${PROJECT_DIR}/vendor/hermes-agent/pyproject.toml" ]] || die "Missing vendor/hermes-agent/pyproject.toml"
}

ensure_packages() {
  log "Installing AlmaLinux packages"
  dnf install -y dnf-plugins-core || true
  dnf install -y \
    git curl ca-certificates openssl tar gzip findutils shadow-utils \
    gcc gcc-c++ make \
    python3.11 python3.11-pip python3.11-devel

  command -v python3.11 >/dev/null 2>&1 || die "python3.11 not found after install"
}

ensure_user_and_dirs() {
  log "Preparing ${RUN_USER} user and ${BASE_DIR}"
  if ! id "${RUN_USER}" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "${BASE_DIR}/home" --shell /bin/bash "${RUN_USER}"
  fi

  mkdir -p "${BASE_DIR}/venvs" "${HERMES_HOME}" "${BASE_DIR}/logs"
  chown -R "${RUN_USER}:${RUN_USER}" "${BASE_DIR}"
}

copy_env_if_missing() {
  log "Preparing env files"
  if [[ ! -f "${HERMES_ENV_FILE}" ]]; then
    install -m 600 "${PROJECT_DIR}/deploy/env/hermes.env.example" "${HERMES_ENV_FILE}"
  fi
  if [[ ! -f "${BOT_ENV_FILE}" ]]; then
    install -m 600 "${PROJECT_DIR}/deploy/env/bot.env.example" "${BOT_ENV_FILE}"
  fi

  chown "${RUN_USER}:${RUN_USER}" "${HERMES_ENV_FILE}" "${BOT_ENV_FILE}"
}

get_env() {
  local file="$1"
  local key="$2"
  if [[ ! -f "${file}" ]]; then
    return 0
  fi
  grep -E "^${key}=" "${file}" | tail -n 1 | cut -d= -f2- || true
}

set_env() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp
  tmp="$(mktemp)"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { done = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      done = 1
      next
    }
    { print }
    END {
      if (!done) {
        print key "=" value
      }
    }
  ' "${file}" > "${tmp}"
  cat "${tmp}" > "${file}"
  rm -f "${tmp}"
}

ensure_api_key_pair() {
  local current
  current="$(get_env "${HERMES_ENV_FILE}" API_SERVER_KEY)"
  if [[ -z "${current}" ]]; then
    current="$(openssl rand -hex 32)"
    set_env "${HERMES_ENV_FILE}" API_SERVER_KEY "${current}"
  fi
  set_env "${BOT_ENV_FILE}" HERMES_API_KEY "${current}"
}

prompt_if_empty() {
  local file="$1"
  local key="$2"
  local prompt="$3"
  local secret="${4:-0}"
  local current value
  current="$(get_env "${file}" "${key}")"
  if [[ -n "${current}" ]]; then
    return 0
  fi
  if [[ "${NO_PROMPT}" -eq 1 ]]; then
    return 0
  fi

  if [[ "${secret}" -eq 1 ]]; then
    read -r -s -p "${prompt}: " value
    printf '\n'
  else
    read -r -p "${prompt}: " value
  fi

  if [[ -n "${value}" ]]; then
    set_env "${file}" "${key}" "${value}"
  fi
}

prompt_provider_defaults() {
  local provider model api_key_name

  provider="$(get_env "${HERMES_ENV_FILE}" HERMES_PROVIDER)"
  model="$(get_env "${HERMES_ENV_FILE}" HERMES_PROVIDER_MODEL)"

  if [[ "${NO_PROMPT}" -eq 0 ]]; then
    read -r -p "Hermes provider [${provider:-deepseek}]: " input_provider
    if [[ -n "${input_provider:-}" ]]; then
      provider="${input_provider}"
      set_env "${HERMES_ENV_FILE}" HERMES_PROVIDER "${provider}"
    fi

    read -r -p "Hermes model [${model:-deepseek-v4-flash}]: " input_model
    if [[ -n "${input_model:-}" ]]; then
      model="${input_model}"
      set_env "${HERMES_ENV_FILE}" HERMES_PROVIDER_MODEL "${model}"
    fi
  fi

  case "${provider:-deepseek}" in
    deepseek) api_key_name="DEEPSEEK_API_KEY" ;;
    gemini|google|google-gemini) api_key_name="GOOGLE_API_KEY" ;;
    openrouter) api_key_name="OPENROUTER_API_KEY" ;;
    openai|openai-api) api_key_name="OPENAI_API_KEY" ;;
    *) api_key_name="" ;;
  esac

  if [[ -n "${api_key_name}" ]]; then
    prompt_if_empty "${HERMES_ENV_FILE}" "${api_key_name}" "${api_key_name} (hidden, Enter to skip)" 1
  fi
}

prompt_required_values() {
  log "Collecting missing config values"
  prompt_if_empty "${BOT_ENV_FILE}" TELEGRAM_BOT_TOKEN "Telegram bot token (hidden, Enter to skip)" 1
  prompt_if_empty "${BOT_ENV_FILE}" ADMIN_USER_IDS "Telegram admin user ID, comma-separated if many" 0
  prompt_provider_defaults
}

write_hermes_config() {
  log "Writing Hermes config.yaml"
  cat > "${HERMES_HOME}/config.yaml" <<EOF
model:
  provider: "\${HERMES_PROVIDER}"
  default: "\${HERMES_PROVIDER_MODEL}"

terminal:
  backend: local
  cwd: "${PROJECT_DIR}"

updates:
  pre_update_backup: false
EOF

  ln -sfn "${HERMES_ENV_FILE}" "${HERMES_HOME}/.env"
  chown -h "${RUN_USER}:${RUN_USER}" "${HERMES_HOME}/.env" || true
  chown "${RUN_USER}:${RUN_USER}" "${HERMES_HOME}/config.yaml"
  chmod 600 "${HERMES_ENV_FILE}" "${BOT_ENV_FILE}"
}

install_python_envs() {
  log "Installing Hermes Python environment"
  if [[ ! -d "${HERMES_VENV}" ]]; then
    python3.11 -m venv "${HERMES_VENV}"
  fi
  "${HERMES_VENV}/bin/python" -m pip install --upgrade pip setuptools wheel
  "${HERMES_VENV}/bin/python" -m pip install -e "${PROJECT_DIR}/vendor/hermes-agent"

  log "Installing Telegram bot Python environment"
  if [[ ! -d "${BOT_VENV}" ]]; then
    python3.11 -m venv "${BOT_VENV}"
  fi
  "${BOT_VENV}/bin/python" -m pip install --upgrade pip setuptools wheel
  "${BOT_VENV}/bin/python" -m pip install -r "${PROJECT_DIR}/telegram-bot/requirements.txt"

  chown -R "${RUN_USER}:${RUN_USER}" "${BASE_DIR}/venvs"
}

write_systemd_services() {
  log "Installing systemd services"
  cat > "${HERMES_SERVICE}" <<EOF
[Unit]
Description=Hermes ADS API Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=${HERMES_ENV_FILE}
Environment=HERMES_HOME=${HERMES_HOME}
Environment=PYTHONUNBUFFERED=1
ExecStart=${HERMES_VENV}/bin/hermes gateway
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

  cat > "${BOT_SERVICE}" <<EOF
[Unit]
Description=Telegram Qualify Post Bot
After=network-online.target hermes-api.service
Wants=network-online.target hermes-api.service

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${PROJECT_DIR}/telegram-bot
EnvironmentFile=${BOT_ENV_FILE}
Environment=PYTHONUNBUFFERED=1
ExecStart=${BOT_VENV}/bin/python -m app.main
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable hermes-api.service telegram-bot.service
}

is_ready_to_start() {
  local token admin api_key provider provider_key
  token="$(get_env "${BOT_ENV_FILE}" TELEGRAM_BOT_TOKEN)"
  admin="$(get_env "${BOT_ENV_FILE}" ADMIN_USER_IDS)"
  api_key="$(get_env "${HERMES_ENV_FILE}" API_SERVER_KEY)"
  provider="$(get_env "${HERMES_ENV_FILE}" HERMES_PROVIDER)"

  [[ -n "${token}" ]] || return 1
  [[ -n "${admin}" ]] || return 1
  [[ -n "${api_key}" ]] || return 1

  case "${provider:-deepseek}" in
    deepseek) provider_key="$(get_env "${HERMES_ENV_FILE}" DEEPSEEK_API_KEY)" ;;
    gemini|google|google-gemini) provider_key="$(get_env "${HERMES_ENV_FILE}" GOOGLE_API_KEY)" ;;
    openrouter) provider_key="$(get_env "${HERMES_ENV_FILE}" OPENROUTER_API_KEY)" ;;
    openai|openai-api) provider_key="$(get_env "${HERMES_ENV_FILE}" OPENAI_API_KEY)" ;;
    *) provider_key="custom-provider-not-checked" ;;
  esac

  [[ -n "${provider_key}" ]]
}

start_or_explain() {
  if is_ready_to_start; then
    log "Starting services"
    systemctl restart hermes-api.service
    sleep 5
    systemctl restart telegram-bot.service
    systemctl --no-pager --full status hermes-api.service telegram-bot.service || true
  else
    cat <<EOF

Install finished, but services were not started because required values are missing.

Edit these files:
  nano ${HERMES_ENV_FILE}
  nano ${BOT_ENV_FILE}

Then run:
  systemctl restart hermes-api telegram-bot
  ${PROJECT_DIR}/deploy/manage.sh status
EOF
  fi
}

main() {
  require_root
  ensure_project_layout
  ensure_packages
  ensure_user_and_dirs
  copy_env_if_missing
  ensure_api_key_pair
  prompt_required_values
  write_hermes_config
  install_python_envs
  write_systemd_services
  start_or_explain

  cat <<EOF

Done.

Useful commands:
  ${PROJECT_DIR}/deploy/manage.sh status
  ${PROJECT_DIR}/deploy/manage.sh logs
  ${PROJECT_DIR}/deploy/manage.sh restart
  ${PROJECT_DIR}/deploy/manage.sh test-hermes
EOF
}

main "$@"
