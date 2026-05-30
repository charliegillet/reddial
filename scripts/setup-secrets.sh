#!/usr/bin/env bash
#
# setup-secrets.sh — push RedDial secrets from a local .env to their homes.
#
# Two targets (pick with the first arg, default: both):
#   pcc   -> Pipecat Cloud secret set (runtime secrets the deployed bot reads)
#   gh    -> GitHub Actions secrets used by .github/workflows/deploy.yml
#
# Usage:
#   scripts/setup-secrets.sh            # do both (pcc + gh)
#   scripts/setup-secrets.sh pcc        # only Pipecat Cloud
#   scripts/setup-secrets.sh gh         # only GitHub Actions
#   ENV_FILE=server/.env scripts/setup-secrets.sh
#   DRY_RUN=1 scripts/setup-secrets.sh  # print what WOULD run, change nothing
#
# Safety:
#   * Fails loudly if .env is missing.
#   * NEVER echoes secret values (only key names).
#   * Idempotent: `pcc secrets set` / `gh secret set` upsert, so re-running is safe.
#   * chmod note: make this executable once with `chmod +x scripts/setup-secrets.sh`.
#
set -euo pipefail

# ── Locate .env ───────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/server/.env}"
TARGET="${1:-both}"
DRY_RUN="${DRY_RUN:-}"

# Pipecat Cloud secret set name — keep in sync with server/pcc-deploy.toml.
PCC_SECRET_SET="${PCC_SECRET_SET:-flower-bot-secrets}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: env file not found: ${ENV_FILE}" >&2
  echo "       Create it first:  cp server/.env.example server/.env  (then fill it in)" >&2
  exit 1
fi

# Runtime secrets the DEPLOYED bot needs (-> Pipecat Cloud secret set).
PCC_KEYS=(
  NVIDIA_ASR_URL
  NEMOTRON_LLM_URL
  NEMOTRON_LLM_API_KEY
  GRADIUM_API_KEY
  GRADIUM_VOICE_ID
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  VERIFIED_CALLER_ID
  PUBLIC_HOST
  CEKURA_API_KEY
  OPENAI_API_KEY
)

# Secrets the DEPLOY WORKFLOW needs (-> GitHub Actions repo/environment secrets).
GH_KEYS=(
  PIPECAT_CLOUD_API_KEY
)

run() {
  if [[ -n "${DRY_RUN}" ]]; then
    echo "DRY_RUN: $*"
  else
    "$@"
  fi
}

# Read a key's value from .env WITHOUT printing it. Returns non-zero if absent
# or empty. Handles `KEY=value` lines, ignores comments/blank lines.
get_env_value() {
  local key="$1"
  # Last matching assignment wins; strip surrounding quotes; never logged.
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n1 || true)"
  [[ -z "${line}" ]] && return 1
  local val="${line#*=}"
  val="${val%%#*}"                       # strip trailing inline comment
  val="$(printf '%s' "${val}" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  val="${val%\"}"; val="${val#\"}"       # strip double quotes
  val="${val%\'}"; val="${val#\'}"       # strip single quotes
  [[ -z "${val}" ]] && return 1
  printf '%s' "${val}"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' not found on PATH" >&2; exit 1; }
}

push_pcc() {
  need_cmd pcc
  echo "==> Pipecat Cloud secret set: ${PCC_SECRET_SET}"
  local set=0 skipped=0 val
  for key in "${PCC_KEYS[@]}"; do
    if val="$(get_env_value "${key}")"; then
      # Value passed via env to avoid it ever appearing in argv/process list.
      run env "REDDIAL_SECRET_VALUE=${val}" \
        sh -c "pcc secrets set \"${PCC_SECRET_SET}\" \"${key}=\$REDDIAL_SECRET_VALUE\""
      echo "    set   ${key}"
      set=$((set + 1))
    else
      echo "    skip  ${key} (empty/absent in ${ENV_FILE##*/})"
      skipped=$((skipped + 1))
    fi
  done
  echo "    -> ${set} set, ${skipped} skipped"
}

push_gh() {
  need_cmd gh
  echo "==> GitHub Actions secrets (environment: production)"
  local set=0 skipped=0 val
  for key in "${GH_KEYS[@]}"; do
    if val="$(get_env_value "${key}")"; then
      # --body reads the value; gh does not echo it back.
      run gh secret set "${key}" --env production --body "${val}"
      echo "    set   ${key}"
      set=$((set + 1))
    else
      echo "    skip  ${key} (empty/absent) — printing the command to run manually:"
      echo "          gh secret set ${key} --env production   # then paste the value when prompted"
      skipped=$((skipped + 1))
    fi
  done
  echo "    -> ${set} set, ${skipped} skipped"
}

echo "RedDial secret setup  (env file: ${ENV_FILE})"
[[ -n "${DRY_RUN}" ]] && echo "(DRY_RUN: no changes will be made)"

case "${TARGET}" in
  pcc)  push_pcc ;;
  gh)   push_gh ;;
  both) push_pcc; echo; push_gh ;;
  *)    echo "ERROR: unknown target '${TARGET}' (use: pcc | gh | both)" >&2; exit 2 ;;
esac

echo "Done. (no secret values were printed)"
