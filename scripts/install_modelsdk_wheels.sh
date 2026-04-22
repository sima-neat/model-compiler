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

latest_patch_for_minor() {
  local py_mm="$1"
  local list_out=""
  if ! list_out="$(pyenv install --list 2>/dev/null)"; then
    return 1
  fi
  echo "$list_out" \
    | sed 's/^[[:space:]]*//' \
    | grep -E "^${py_mm//./\\.}\\.[0-9]+$" \
    | sort -V \
    | tail -n1
}

ensure_python_cmd() {
  local py_mm="$1"
  local cmd=""
  if cmd="$(resolve_python_cmd "$py_mm")"; then
    echo "$cmd"
    return 0
  fi

  local pyenv_root="${PYENV_ROOT:-$HOME/.pyenv}"
  export PYENV_ROOT="$pyenv_root"
  export PATH="$PYENV_ROOT/bin:$PATH"

  if ! command -v pyenv >/dev/null 2>&1; then
    echo "Python ${py_mm} not found; attempting to install pyenv..." >&2
    if [[ -x "$PYENV_ROOT/bin/pyenv" ]]; then
      :
    else
      if ! command -v curl >/dev/null 2>&1; then
        echo "curl is required to install pyenv automatically." >&2
        return 1
      fi
      if ! command -v bash >/dev/null 2>&1; then
        echo "bash is required to install pyenv automatically." >&2
        return 1
      fi
      if ! (curl -fsSL https://pyenv.run | bash) >&2; then
        echo "Failed to install pyenv automatically." >&2
        return 1
      fi
    fi
    export PATH="$PYENV_ROOT/bin:$PATH"
  fi

  if ! command -v pyenv >/dev/null 2>&1; then
    echo "pyenv is not available after installation attempt." >&2
    return 1
  fi

  local target_version=""
  target_version="$(latest_patch_for_minor "$py_mm" || true)"
  if [[ -z "$target_version" ]]; then
    target_version="$py_mm"
  fi

  echo "Installing Python ${target_version} via pyenv..." >&2
  if ! pyenv install -s "$target_version" >&2; then
    echo "pyenv failed to install Python ${target_version}." >&2
    return 1
  fi

  local pybin="$PYENV_ROOT/versions/$target_version/bin/python"
  if [[ -x "$pybin" ]]; then
    echo "$pybin"
    return 0
  fi

  # Fallback: check direct minor directory.
  pybin="$PYENV_ROOT/versions/$py_mm/bin/python"
  if [[ -x "$pybin" ]]; then
    echo "$pybin"
    return 0
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

if ! PYTHON_CMD="$(ensure_python_cmd "$PYTHON_MM")"; then
  echo "Python ${PYTHON_MM} is not available and could not be installed automatically." >&2
  echo "Install Python ${PYTHON_MM} (or pyenv build dependencies) and retry." >&2
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

echo "Installing ${#wheels[@]} wheel(s) from $SCRIPT_DIR into $VENV_DIR (with dependency resolution)"
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check --no-index --find-links "$SCRIPT_DIR" "${wheels[@]}"
echo "ModelSDK wheel installation complete in $VENV_DIR."
