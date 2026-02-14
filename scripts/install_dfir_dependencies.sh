#!/usr/bin/env bash
set -euo pipefail

# Best-effort dependency installer for EviForge forensic tooling.
# It installs what is available on this host and prints actionable skips.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-$ROOT_DIR/.venv/bin/pip}"

if [[ "${1:-}" != "--apply" ]]; then
  cat <<'EOF'
Dry-run mode.

This script will install:
  - Python modules: volatility3, scapy, pandas
  - System binaries: yara, foremost, ssdeep
  - Optional (best-effort): zeek, suricata

Run with:
  bash scripts/install_dfir_dependencies.sh --apply
EOF
  exit 0
fi

if [[ ! -x "$PIP_BIN" ]]; then
  echo "Missing pip in venv: $PIP_BIN" >&2
  exit 1
fi

echo "[1/4] Installing Python forensic modules into venv..."
"$PIP_BIN" install --disable-pip-version-check volatility3 scapy pandas

if command -v sudo >/dev/null 2>&1; then
  echo "[2/4] Updating apt package lists..."
  sudo apt-get update

  echo "[3/4] Installing core DFIR binaries..."
  sudo apt-get install -y yara foremost ssdeep

  echo "[4/4] Installing optional network stack (best effort: zeek/suricata)..."
  if ! sudo apt-get install -y zeek suricata; then
    echo "Optional install skipped: zeek/suricata have unmet dependencies on this host."
  fi
else
  echo "sudo not found; skipped system package install."
fi

echo
echo "Installed tool summary:"
for tool in yara foremost ssdeep zeek suricata; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf "  %-10s %s\n" "$tool" "$(command -v "$tool")"
  else
    printf "  %-10s %s\n" "$tool" "MISSING"
  fi
done

echo
echo "Python module summary:"
"$PYTHON_BIN" - <<'PY'
import importlib.util
for module in ["volatility3", "scapy", "pandas"]:
    print(f"  {module:<12} {'OK' if importlib.util.find_spec(module) else 'MISSING'}")
PY

