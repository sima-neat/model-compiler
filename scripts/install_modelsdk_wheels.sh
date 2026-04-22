#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_JSON="$SCRIPT_DIR/source.json"

normalize_python_version() {
  local raw="$1"
  raw="$(echo "$raw" | tr -d '[:space:]')"
  if [[ "$raw" =~ ^[0-9]+\.[0-9]+$ ]]; then
    echo "$raw"
    return 0
  fi
  if [[ "$raw" =~ ^[0-9]{3}$ ]]; then
    echo "${raw:0:1}.${raw:1:2}"
    return 0
  fi
  if [[ "$raw" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$(echo "$raw" | awk -F. '{print $1"."$2}')"
    return 0
  fi
  return 1
}

resolve_python_cmd() {
  local py_mm="$1"
  local major="${py_mm%%.*}"
  local minor="${py_mm##*.}"
  local cmd=""

  if command -v "python${major}.${minor}" >/dev/null 2>&1; then
    echo "python${major}.${minor}"
    return 0
  fi
  if command -v "python${major}" >/dev/null 2>&1; then
    cmd="python${major}"
    if "$cmd" -c "import sys; raise SystemExit(0 if (sys.version_info.major, sys.version_info.minor)==(${major},${minor}) else 1)" >/dev/null 2>&1; then
      echo "$cmd"
      return 0
    fi
  fi
  if command -v python3 >/dev/null 2>&1; then
    cmd="python3"
    if "$cmd" -c "import sys; raise SystemExit(0 if (sys.version_info.major, sys.version_info.minor)==(${major},${minor}) else 1)" >/dev/null 2>&1; then
      echo "$cmd"
      return 0
    fi
  fi
  return 1
}

normalize_arch() {
  local raw="$1"
  case "$raw" in
    x86_64|amd64) echo "x86_64" ;;
    aarch64|arm64) echo "aarch64" ;;
    *) echo "$raw" ;;
  esac
}

wheel_platform_tag() {
  local wheel="$1"
  local base
  base="$(basename "$wheel")"
  base="${base%.whl}"
  IFS='-' read -r -a parts <<< "$base"
  if [[ ${#parts[@]} -lt 5 ]]; then
    echo ""
    return 1
  fi
  echo "${parts[${#parts[@]}-1]}"
}

wheel_arch_compatible() {
  local wheel="$1"
  local host_arch="$2"
  local plat
  plat="$(wheel_platform_tag "$wheel")"
  if [[ -z "$plat" ]]; then
    return 1
  fi

  # Pure wheels are architecture-independent.
  if [[ "$plat" == "any" ]]; then
    return 0
  fi

  local p="${plat,,}"
  case "$host_arch" in
    x86_64)
      [[ "$p" == *"x86_64"* || "$p" == *"amd64"* ]]
      ;;
    aarch64)
      [[ "$p" == *"aarch64"* || "$p" == *"arm64"* ]]
      ;;
    *)
      return 1
      ;;
  esac
}

if [[ ! -f "$SOURCE_JSON" ]]; then
  echo "Missing source.json next to installer: $SOURCE_JSON" >&2
  exit 1
fi

PYTHON_VERSION_RAW="$(
  python3 -c '
import json,sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    doc = json.load(f)
v = doc.get("python_version", "")
print(v if isinstance(v, str) else "")
' "$SOURCE_JSON"
)"

if [[ -z "$PYTHON_VERSION_RAW" ]]; then
  echo "python_version is missing in $SOURCE_JSON" >&2
  exit 1
fi

if ! PYTHON_MM="$(normalize_python_version "$PYTHON_VERSION_RAW")"; then
  echo "Unsupported python_version in $SOURCE_JSON: '$PYTHON_VERSION_RAW'" >&2
  exit 1
fi

if ! PYTHON_CMD="$(resolve_python_cmd "$PYTHON_MM")"; then
  echo "Python ${PYTHON_MM} is not available on PATH." >&2
  exit 1
fi

wheels=()
while IFS= read -r wheel; do
  [[ -n "$wheel" ]] && wheels+=("$wheel")
done < <(find "$SCRIPT_DIR" -maxdepth 1 -type f -name '*.whl' | sort)
if [[ ${#wheels[@]} -eq 0 ]]; then
  echo "No wheel files found in $SCRIPT_DIR" >&2
  exit 1
fi

HOST_ARCH_RAW="$(uname -m 2>/dev/null || echo unknown)"
HOST_ARCH="$(normalize_arch "$HOST_ARCH_RAW")"
if [[ "$HOST_ARCH" != "x86_64" && "$HOST_ARCH" != "aarch64" ]]; then
  echo "Unsupported system architecture: $HOST_ARCH_RAW" >&2
  exit 1
fi

bad_wheels=()
for wheel in "${wheels[@]}"; do
  if ! wheel_arch_compatible "$wheel" "$HOST_ARCH"; then
    bad_wheels+=("$(basename "$wheel")")
  fi
done

if [[ ${#bad_wheels[@]} -gt 0 ]]; then
  echo "Found wheel(s) incompatible with host architecture '$HOST_ARCH' (uname -m: $HOST_ARCH_RAW):" >&2
  for w in "${bad_wheels[@]}"; do
    echo "  - $w" >&2
  done
  echo "Refusing to install mixed/mismatched architecture wheels." >&2
  exit 1
fi

if [[ -d "/sdk-add-on" && -w "/sdk-add-on" ]]; then
  ADDON_DIR="/sdk-add-on"
else
  ADDON_DIR="${HOME}/sdk-add-on"
  mkdir -p "$ADDON_DIR"
fi

VENV_DIR="${ADDON_DIR}/venv"
echo "Creating virtual environment at: $VENV_DIR (python: $PYTHON_CMD, arch: $HOST_ARCH)"
"$PYTHON_CMD" -m venv "$VENV_DIR"

echo "Installing ${#wheels[@]} wheel(s) from $SCRIPT_DIR into $VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check --no-index --find-links "$SCRIPT_DIR" "${wheels[@]}"
echo "ModelSDK wheel installation complete in $VENV_DIR."
