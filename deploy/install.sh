#!/usr/bin/env bash
# Install the tenomi-bridge package into a venv.
# Default: venv + pip + config.toml (does not register systemd).
# After a foreground smoke test:
#   bash deploy/install.sh --enable
set -euo pipefail

usage() {
  cat <<'EOF'
usage: bash deploy/install.sh [--enable]

  (default)  create venv, pip install, write config.toml if missing
  --enable   register systemd and start the service
EOF
}

ENABLE=0
for arg in "$@"; do
  case "$arg" in
    --enable) ENABLE=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="${TENOMI_ROOT:-$ROOT}"
PYTHON="${TENOMI_PYTHON:-python3}"
VENV="$ROOT/.venv"

if [[ "${EUID}" -eq 0 ]]; then
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    RUN_USER="${TENOMI_USER:-$SUDO_USER}"
  else
    echo "run as the Linux user that owns the venv, not as root:" >&2
    echo "  bash deploy/install.sh" >&2
    exit 1
  fi
else
  RUN_USER="${TENOMI_USER:-$(id -un)}"
fi
RUN_GROUP="$(id -gn "$RUN_USER")"

UNIT_IN="$ROOT/deploy/tenomi-bridge.service.in"
UNIT_DST="/etc/systemd/system/tenomi-bridge.service"
EXAMPLE="$ROOT/config.example.toml"
CONFIG="$ROOT/config.toml"

if [[ ! -f "$ROOT/pyproject.toml" ]]; then
  echo "missing pyproject.toml under $ROOT" >&2
  exit 1
fi
if [[ ! -f "$EXAMPLE" ]]; then
  echo "missing $EXAMPLE" >&2
  exit 1
fi

if [[ ! -x "$VENV/bin/python3" ]]; then
  echo "creating venv $VENV"
fi
"$PYTHON" -m venv --prompt tenomi "$VENV"

echo "pip install $ROOT"
"$VENV/bin/python3" -m pip install --upgrade pip
"$VENV/bin/python3" -m pip install "$ROOT"

if [[ ! -x "$VENV/bin/tenomi-bridge" ]]; then
  echo "missing $VENV/bin/tenomi-bridge after pip install" >&2
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  cp "$EXAMPLE" "$CONFIG"
  echo "created $CONFIG from example; confirm name/port if needed"
fi

echo "install user=$RUN_USER group=$RUN_GROUP root=$ROOT"

if [[ "$ENABLE" -eq 0 ]]; then
  echo "package ready. smoke-test, then enable the service:"
  echo "  source $VENV/bin/activate"
  echo "  tenomi-bridge --config $CONFIG"
  echo "  bash deploy/install.sh --enable"
  exit 0
fi

if [[ ! -f "$UNIT_IN" ]]; then
  echo "missing unit template: $UNIT_IN" >&2
  exit 1
fi

UNIT_TMP="$(mktemp)"
trap 'rm -f "$UNIT_TMP"' EXIT
sed \
  -e "s|__USER__|${RUN_USER}|g" \
  -e "s|__GROUP__|${RUN_GROUP}|g" \
  -e "s|__ROOT__|${ROOT}|g" \
  "$UNIT_IN" > "$UNIT_TMP"

sudo cp "$UNIT_TMP" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable tenomi-bridge.service
sudo systemctl restart tenomi-bridge.service
sudo systemctl --no-pager --full status tenomi-bridge.service
