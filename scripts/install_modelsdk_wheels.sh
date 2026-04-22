#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_JSON="$SCRIPT_DIR/source.json"
EXTRA_INDEX_URL="${EXTRA_INDEX_URL:-https://pypi.org/simple}"

read_source_json_field() {
  local expr="$1"
  python3 -c '
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    doc = json.load(f)
expr = sys.argv[2]
if expr == "python_version":
    v = doc.get("python_version", "")
    print(v if isinstance(v, str) else "")
elif expr == "system_dependencies_ubuntu":
    deps = (((doc.get("system_dependencies") or {}).get("ubuntu")) or [])
    if not isinstance(deps, list):
        raise SystemExit(0)
    for item in deps:
        if isinstance(item, str) and item.strip():
            print(item.strip())
elif expr == "binary_package_archives":
    items = doc.get("binary-packages", [])
    if not isinstance(items, list):
        raise SystemExit(0)
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().strip("/")
        version = str(item.get("version", "")).strip()
        extension = str(item.get("extension", "")).strip()
        archive_type = str(item.get("archive-type", "zip")).strip() or "zip"
        if extension:
            if extension.startswith("."):
                archive_type = extension[1:]
            else:
                archive_type = extension
        if name and version:
            base = name.rsplit("/", 1)[-1]
            print(f"{base}-{version}.{archive_type}")
' "$SOURCE_JSON" "$expr"
}

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

install_system_dependencies() {
  local distro_id=""
  local deps=()
  local dep=""
  local missing=()
  local installer=()

  if [[ ! -f /etc/os-release ]]; then
    return 0
  fi

  distro_id="$(
    . /etc/os-release
    printf '%s' "${ID:-}"
  )"

  case "$distro_id" in
    ubuntu|debian)
      while IFS= read -r dep; do
        [[ -n "$dep" ]] && deps+=("$dep")
      done < <(read_source_json_field "system_dependencies_ubuntu")
      ;;
    *)
      return 0
      ;;
  esac

  if [[ ${#deps[@]} -eq 0 ]]; then
    return 0
  fi

  for dep in "${deps[@]}"; do
    if ! dpkg -s "$dep" >/dev/null 2>&1; then
      missing+=("$dep")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi

  echo "Installing required system packages: ${missing[*]}" >&2
  if [[ "$(id -u)" -eq 0 ]]; then
    installer=(apt-get)
  elif command -v sudo >/dev/null 2>&1; then
    installer=(sudo apt-get)
  else
    echo "Missing required system packages: ${missing[*]}" >&2
    echo "Please install them manually and retry." >&2
    return 1
  fi

  "${installer[@]}" update >&2
  "${installer[@]}" install -y "${missing[@]}" >&2
}

install_binary_packages() {
  local target_root="$1"
  local archives=()
  local archive=""
  local tmpdir=""
  local archive_path=""
  local extract_root=""

  while IFS= read -r archive; do
    [[ -n "$archive" ]] && archives+=("$archive")
  done < <(read_source_json_field "binary_package_archives")

  if [[ ${#archives[@]} -eq 0 ]]; then
    return 0
  fi

  for archive in "${archives[@]}"; do
    archive_path="${SCRIPT_DIR}/${archive}"
    if [[ ! -f "$archive_path" ]]; then
      echo "Binary package archive not found: $archive_path" >&2
      return 1
    fi

    tmpdir="$(mktemp -d)"
    python3 - "$archive_path" "$tmpdir" <<'PY'
import pathlib
import sys
import zipfile

archive = pathlib.Path(sys.argv[1])
dest = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(archive) as zf:
    zf.extractall(dest)
PY

    extract_root="$tmpdir"
    if [[ ! -d "$extract_root/bin" && ! -d "$extract_root/include" && ! -d "$extract_root/lib" ]]; then
      first_dir="$(find "$tmpdir" -mindepth 1 -maxdepth 1 -type d | head -n1 || true)"
      if [[ -n "$first_dir" ]]; then
        extract_root="$first_dir"
      fi
    fi

    echo "Installing binary package archive into ${target_root}: $archive" >&2
    mkdir -p "${target_root}/bin" "${target_root}/include" "${target_root}/lib"
    if [[ -d "$extract_root/bin" ]]; then
      cp -a "$extract_root/bin/." "${target_root}/bin/"
      find "${target_root}/bin" -maxdepth 1 -type f -exec chmod a+rx {} +
    fi
    if [[ -d "$extract_root/include" ]]; then
      cp -a "$extract_root/include/." "${target_root}/include/"
    fi
    if [[ -d "$extract_root/lib" ]]; then
      cp -a "$extract_root/lib/." "${target_root}/lib/"
    fi

    rm -rf "$tmpdir"
  done
}

configure_shell_path() {
  local bin_dir="$1"
  local lib_dir="$2"
  local bashrc="${HOME}/.bashrc"
  local bash_profile="${HOME}/.bash_profile"
  local target_file=""
  local marker_begin="# >>> modelsdk path >>>"
  local marker_end="# <<< modelsdk path <<<"

  if [[ -f "$bashrc" || ! -f "$bash_profile" ]]; then
    target_file="$bashrc"
  else
    target_file="$bash_profile"
  fi

  touch "$target_file"

  if grep -Fq "$marker_begin" "$target_file"; then
    return 0
  fi

  cat >> "$target_file" <<EOF
$marker_begin
if [ -d "$bin_dir" ] && [[ ":\$PATH:" != *":$bin_dir:"* ]]; then
  export PATH="$bin_dir:\$PATH"
fi
if [ -d "$lib_dir" ] && [[ ":\${LD_LIBRARY_PATH:-}:" != *":$lib_dir:"* ]]; then
  export LD_LIBRARY_PATH="$lib_dir\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
fi
$marker_end
EOF
}

cleanup_downloaded_resources() {
  local archive=""
  local archive_path=""
  local extracted_dir=""
  local removed=0

  while IFS= read -r archive; do
    [[ -n "$archive" ]] || continue
    archive_path="${SCRIPT_DIR}/${archive}"
    extracted_dir="${SCRIPT_DIR}/${archive%.*}"

    if [[ -f "$archive_path" ]]; then
      rm -f "$archive_path"
      removed=1
    fi
    if [[ -d "$extracted_dir" ]]; then
      rm -rf "$extracted_dir"
      removed=1
    fi
  done < <(read_source_json_field "binary_package_archives")

  while IFS= read -r wheel; do
    [[ -n "$wheel" ]] || continue
    rm -f "$wheel"
    removed=1
  done < <(find "$SCRIPT_DIR" -maxdepth 1 -type f -name '*.whl' | sort)

  if [[ "$removed" -eq 1 ]]; then
    echo "Removed downloaded bundle resources from $SCRIPT_DIR."
  else
    echo "No downloaded bundle resources needed cleanup in $SCRIPT_DIR."
  fi
}

if [[ ! -f "$SOURCE_JSON" ]]; then
  echo "Missing source.json next to installer: $SOURCE_JSON" >&2
  exit 1
fi

PYTHON_VERSION_RAW="$(read_source_json_field "python_version")"

if [[ -z "$PYTHON_VERSION_RAW" ]]; then
  echo "python_version is missing in $SOURCE_JSON" >&2
  exit 1
fi

if ! PYTHON_MM="$(normalize_python_version "$PYTHON_VERSION_RAW")"; then
  echo "Unsupported python_version in $SOURCE_JSON: '$PYTHON_VERSION_RAW'" >&2
  exit 1
fi

if ! install_system_dependencies; then
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

if [[ -d "/sdk-extensions" && -w "/sdk-extensions" ]]; then
  EXTENSIONS_DIR="/sdk-extensions"
elif [[ -d "/sdk-add-on" && -w "/sdk-add-on" ]]; then
  # Backward-compatible fallback for older layouts.
  EXTENSIONS_DIR="/sdk-add-on"
else
  EXTENSIONS_DIR="${HOME}/sdk-extensions"
  mkdir -p "$EXTENSIONS_DIR"
fi

MODELSDK_DIR="${EXTENSIONS_DIR}/model-sdk"
mkdir -p "$MODELSDK_DIR"
VENV_DIR="${MODELSDK_DIR}/venv"
echo "Creating virtual environment at: $VENV_DIR (python: $PYTHON_CMD, arch: $HOST_ARCH)"
"$PYTHON_CMD" -m venv "$VENV_DIR"

if ! install_binary_packages "$VENV_DIR"; then
  exit 1
fi

echo "Installing ${#wheels[@]} wheel(s) from $SCRIPT_DIR into $VENV_DIR (with dependency resolution)"
pip_args=(
  --disable-pip-version-check
  --find-links "$SCRIPT_DIR"
)
if [[ -n "$EXTRA_INDEX_URL" ]]; then
  pip_args+=(--extra-index-url "$EXTRA_INDEX_URL")
fi
"$VENV_DIR/bin/python" -m pip install "${pip_args[@]}" "${wheels[@]}"
configure_shell_path "$VENV_DIR/bin" "$VENV_DIR/lib"
cleanup_downloaded_resources
echo "ModelSDK wheel installation complete in $VENV_DIR."
