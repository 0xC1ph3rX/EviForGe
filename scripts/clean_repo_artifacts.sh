#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/clean_repo_artifacts.sh [--apply] [--root <path>]

Defaults to dry-run mode.
  --apply        Delete matched artifacts.
  --root <path>  Repository root to clean (default: current directory).
  -h, --help     Show this help text.
EOF
}

APPLY=0
ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      shift
      ;;
    --root)
      if [[ $# -lt 2 ]]; then
        echo "error: --root requires a path" >&2
        exit 2
      fi
      ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  ROOT="."
fi

ROOT="$(cd "$ROOT" && pwd)"

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: '$ROOT' is not a git working tree" >&2
  exit 2
fi

to_rel() {
  local abs="$1"
  if [[ "$abs" == "$ROOT" ]]; then
    printf "."
    return
  fi
  printf "%s" "${abs#"$ROOT"/}"
}

is_explicit_nontarget() {
  local rel="$1"
  [[ "$rel" == ".venv" || "$rel" == .venv/* || "$rel" == "site" || "$rel" == site/* || "$rel" == "dump.rdb" || "$rel" == "verify_expansion.py" ]]
}

is_tracked() {
  local abs="$1"
  local rel
  rel="$(to_rel "$abs")"

  if git -C "$ROOT" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1; then
    return 0
  fi

  if [[ -d "$abs" ]]; then
    if [[ -n "$(git -C "$ROOT" ls-files -- "$rel")" ]]; then
      return 0
    fi
  fi
  return 1
}

declare -a CANDIDATES=()

if [[ -e "$ROOT/.eviforge" ]]; then
  CANDIDATES+=("$ROOT/.eviforge")
fi
if [[ -e "$ROOT/.pytest_cache" ]]; then
  CANDIDATES+=("$ROOT/.pytest_cache")
fi
if [[ -e "$ROOT/core" ]]; then
  CANDIDATES+=("$ROOT/core")
fi
while IFS= read -r -d '' p; do
  CANDIDATES+=("$p")
done < <(find "$ROOT" -maxdepth 1 -type f -name 'core.*' -print0)

while IFS= read -r -d '' p; do
  CANDIDATES+=("$p")
done < <(find "$ROOT" -path "$ROOT/.venv" -prune -o -type d -name '__pycache__' -print0)

while IFS= read -r -d '' p; do
  CANDIDATES+=("$p")
done < <(find "$ROOT" -path "$ROOT/.venv" -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0)

declare -A SEEN=()
declare -a UNIQUE=()
for c in "${CANDIDATES[@]}"; do
  if [[ -z "${SEEN["$c"]:-}" ]]; then
    SEEN["$c"]=1
    UNIQUE+=("$c")
  fi
done

if [[ "${#UNIQUE[@]}" -eq 0 ]]; then
  echo "No matching artifacts found under $ROOT"
  exit 0
fi

IFS=$'\n' SORTED=($(printf '%s\n' "${UNIQUE[@]}" | sort))
unset IFS

echo "Repository: $ROOT"
if [[ "$APPLY" -eq 1 ]]; then
  echo "Mode: APPLY"
else
  echo "Mode: DRY-RUN"
fi

for abs in "${SORTED[@]}"; do
  if [[ ! -e "$abs" ]]; then
    continue
  fi
  rel="$(to_rel "$abs")"

  if is_explicit_nontarget "$rel"; then
    echo "[SKIP nontarget] $rel"
    continue
  fi

  if is_tracked "$abs"; then
    echo "[SKIP tracked] $rel"
    continue
  fi

  if [[ "$APPLY" -eq 1 ]]; then
    rm -rf -- "$abs"
    echo "[DELETED] $rel"
  else
    echo "[DRY-RUN] $rel"
  fi
done
