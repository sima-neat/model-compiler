#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_bundle_dir() {
  if [[ -f "$SCRIPT_DIR/manifest.txt" ]]; then
    echo "$SCRIPT_DIR"
    return 0
  fi
  if [[ -f "$SCRIPT_DIR/../dist/manifest.txt" || -f "$SCRIPT_DIR/../dist/source.json" ]]; then
    (cd "$SCRIPT_DIR/../dist" && pwd)
    return 0
  fi
  echo "$SCRIPT_DIR"
}

BUNDLE_DIR="$(resolve_bundle_dir)"
SOURCE_JSON="$BUNDLE_DIR/source.json"
WHEEL_MANIFEST="$BUNDLE_DIR/manifest.txt"
EXTRA_INDEX_URL="${EXTRA_INDEX_URL:-https://pypi.org/simple}"
WHEEL_LINK_DIR=""
MANIFEST_WHEELS=()
MANIFEST_WHEEL_NAMES=()
MANIFEST_LINK_WHEELS=()

cleanup_temp_resources() {
  if [[ -n "${WHEEL_LINK_DIR:-}" && -d "$WHEEL_LINK_DIR" ]]; then
    rm -rf "$WHEEL_LINK_DIR"
  fi
}
trap cleanup_temp_resources EXIT

read_source_json_field() {
  local expr="$1"
  python3 -c '
import json, os, platform, sys

def normalize_arch(raw):
    raw = str(raw or "").strip().lower()
    if raw in {"x86_64", "amd64"}:
        return "x86_64"
    if raw in {"aarch64", "arm64"}:
        return "aarch64"
    return ""

with open(sys.argv[1], "r", encoding="utf-8") as f:
    doc = json.load(f)
expr = sys.argv[2]
target_arch = normalize_arch(
    os.environ.get("MODELSDK_TARGET_ARCH")
    or os.environ.get("HOST_ARCH")
    or platform.machine()
)
arch_doc = doc.get(target_arch)
if not isinstance(arch_doc, dict):
    arch_doc = {}

def arch_or_top_level(key, default):
    value = arch_doc.get(key, None)
    if value is not None:
        return value
    return doc.get(key, default)

if expr == "python_version":
    v = doc.get("python_version", "")
    print(v if isinstance(v, str) else "")
elif expr == "system_dependencies_ubuntu":
    system_dependencies = arch_or_top_level("system_dependencies", doc.get("system_dependencies") or {})
    deps = (((system_dependencies or {}).get("ubuntu")) or [])
    if not isinstance(deps, list):
        raise SystemExit(0)
    for item in deps:
        if isinstance(item, str) and item.strip():
            print(item.strip())
elif expr == "binary_package_archives":
    items = arch_or_top_level("binary-packages", [])
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
elif expr == "python_package_specs":
    items = arch_or_top_level("python-packages", doc.get("components", []))
    if not isinstance(items, list):
        raise SystemExit(0)
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        version = str(item.get("version", "")).strip()
        if name and version:
            print(f"{name}=={version}")
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

host_multiarch_triplet() {
  local dpkg_arch=""
  if command -v dpkg >/dev/null 2>&1; then
    dpkg_arch="$(dpkg --print-architecture 2>/dev/null || true)"
    case "$dpkg_arch" in
      amd64) echo "x86_64-linux-gnu"; return 0 ;;
      arm64) echo "aarch64-linux-gnu"; return 0 ;;
    esac
  fi

  case "$(uname -m 2>/dev/null || echo unknown)" in
    x86_64|amd64) echo "x86_64-linux-gnu" ;;
    aarch64|arm64) echo "aarch64-linux-gnu" ;;
    *) echo "" ;;
  esac
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

python_stdlib_extensions_ok() {
  local py_cmd="$1"
  "$py_cmd" - <<'PY' >/dev/null 2>&1
import bz2
import ctypes
import lzma
import sqlite3
import ssl
print("ok")
PY
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

host_cxxflags() {
  local flags=()
  local version_dir=""
  local multiarch=""
  local dir=""

  for dir in /usr/include/c++/*; do
    if [[ -d "$dir" ]]; then
      version_dir="$dir"
    fi
  done
  if [[ -n "$version_dir" ]]; then
    flags+=("-isystem" "$version_dir")
    multiarch="$(host_multiarch_triplet)"
    if [[ -n "$multiarch" && -d "/usr/include/${multiarch}/c++/${version_dir##*/}" ]]; then
      flags+=("-isystem" "/usr/include/${multiarch}/c++/${version_dir##*/}")
    fi
  fi

  printf '%s\n' "${flags[*]}"
}

run_host_build_env() {
  local cmd=("$@")
  local host_path="/usr/bin:/bin:$PATH"
  local host_multiarch=""
  local host_pkgconfig_libdir="/usr/lib/pkgconfig:/usr/share/pkgconfig"
  local host_include_path="/usr/include"
  local host_library_path="/lib:/usr/lib"
  local host_cxxflags_value=""
  local host_cmake_args="-DGGML_NATIVE=OFF -DLLAVA_BUILD=OFF"

  host_multiarch="$(host_multiarch_triplet)"
  if [[ -n "$host_multiarch" ]]; then
    host_pkgconfig_libdir="/usr/lib/${host_multiarch}/pkgconfig:${host_pkgconfig_libdir}"
    host_include_path="/usr/include:/usr/include/${host_multiarch}"
    host_library_path="/lib/${host_multiarch}:/usr/lib/${host_multiarch}:${host_library_path}"
  fi
  host_cxxflags_value="$(host_cxxflags)"

  env \
    -u CC \
    -u CXX \
    -u CPP \
    -u LD \
    -u AR \
    -u AS \
    -u NM \
    -u RANLIB \
    -u READELF \
    -u STRIP \
    -u OBJCOPY \
    -u OBJDUMP \
    -u PKG_CONFIG \
    -u PKG_CONFIG_PATH \
    -u PKG_CONFIG_LIBDIR \
    -u PKG_CONFIG_SYSROOT_DIR \
    -u PKG_CONFIG_SYSTEM_INCLUDE_PATH \
    -u PKG_CONFIG_SYSTEM_LIBRARY_PATH \
    -u CFLAGS \
    -u CPPFLAGS \
    -u CXXFLAGS \
    -u LDFLAGS \
    -u CONFIGURE_FLAGS \
    -u CONFIG_SITE \
    -u CMAKE_ARGS \
    -u CMAKE_TOOLCHAIN_FILE \
    -u CMAKE_GENERATOR \
    -u CMAKE_PREFIX_PATH \
    -u CMAKE_LIBRARY_PATH \
    -u CMAKE_INCLUDE_PATH \
    -u HOST \
    -u HOSTARCH \
    -u BUILD_ARCH \
    -u TARGET \
    -u TARGET_ARCH \
    -u TARGET_SYS \
    -u CROSS_COMPILE \
    -u ARCH \
    -u MACHINE \
    -u BUILD_SYS \
    -u HOST_SYS \
    -u TARGET_PREFIX \
    -u OECORE_TARGET_ARCH \
    -u OECORE_TARGET_OS \
    -u OECORE_TARGET_BITS \
    -u OECORE_TARGET_SYSROOT \
    -u OECORE_NATIVE_SYSROOT \
    -u OECORE_ACLOCAL_OPTS \
    -u OECORE_BASELIB \
    -u OECORE_DISTRO_VERSION \
    -u OECORE_SDK_VERSION \
    -u SDKTARGETSYSROOT \
    -u SDKPATH \
    -u PYTHONHOME \
    -u PYTHONPATH \
    PATH="$host_path" \
    PKG_CONFIG_PATH="" \
    PKG_CONFIG_LIBDIR="$host_pkgconfig_libdir" \
    PKG_CONFIG_SYSROOT_DIR="" \
    PKG_CONFIG_SYSTEM_INCLUDE_PATH="$host_include_path" \
    PKG_CONFIG_SYSTEM_LIBRARY_PATH="$host_library_path" \
    CMAKE_ARGS="$host_cmake_args" \
    CXXFLAGS="$host_cxxflags_value" \
    CC=gcc \
    CXX=g++ \
    CPP="gcc -E" \
    LD=ld \
    AR=ar \
    AS=as \
    NM=nm \
    RANLIB=ranlib \
    READELF=readelf \
    STRIP=strip \
    OBJCOPY=objcopy \
    OBJDUMP=objdump \
    "${cmd[@]}"
}

ensure_python_cmd() {
  local py_mm="$1"
  local cmd=""

  local pyenv_root="${PYENV_ROOT:-$HOME/.pyenv}"
  export PYENV_ROOT="$pyenv_root"
  export PATH="$PYENV_ROOT/bin:$PATH"

  if cmd="$(resolve_python_cmd "$py_mm")"; then
    if python_stdlib_extensions_ok "$cmd"; then
      echo "$cmd"
      return 0
    fi
    echo "Python ${py_mm} was found at $cmd, but required stdlib extension modules are missing." >&2
    if [[ "$cmd" == "$PYENV_ROOT"/versions/*/bin/python* ]]; then
      echo "Will try to rebuild that pyenv Python with the required system development packages present." >&2
    else
      echo "The detected Python is not a pyenv-managed installation. Please install a complete Python ${py_mm} and retry." >&2
      return 1
    fi
  fi

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

  local pybin="$PYENV_ROOT/versions/$target_version/bin/python"
  if [[ -x "$pybin" ]] && ! python_stdlib_extensions_ok "$pybin"; then
    echo "Existing pyenv Python ${target_version} is incomplete; rebuilding it." >&2
    run_host_build_env pyenv uninstall -f "$target_version" >&2 || true
  fi

  echo "Installing Python ${target_version} via pyenv..." >&2
  if ! run_host_build_env pyenv install -s "$target_version" >&2; then
    echo "pyenv failed to install Python ${target_version}." >&2
    return 1
  fi

  pybin="$PYENV_ROOT/versions/$target_version/bin/python"
  if [[ -x "$pybin" ]]; then
    if ! python_stdlib_extensions_ok "$pybin"; then
      echo "Python ${target_version} was installed, but required stdlib extension modules are still missing." >&2
      echo "Please verify system packages such as libffi-dev, libbz2-dev, liblzma-dev, libsqlite3-dev, and libssl-dev are available in this environment." >&2
      return 1
    fi
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

  local p
  p="$(printf '%s' "$plat" | tr '[:upper:]' '[:lower:]')"
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

load_manifest_wheels() {
  local manifest="$1"
  local entry=""
  local decoded_entry=""
  local escaped_entry=""
  local link_name=""
  local wheel_path=""

  MANIFEST_WHEELS=()
  MANIFEST_WHEEL_NAMES=()

  if [[ ! -f "$manifest" ]]; then
    echo "Missing wheel manifest in bundle directory: $manifest" >&2
    return 1
  fi

  while IFS= read -r entry || [[ -n "$entry" ]]; do
    entry="${entry//$'\r'/}"
    [[ -n "$entry" ]] || continue

    if [[ "$entry" == */* || "$entry" == "."* || "$entry" != *.whl ]]; then
      echo "Invalid wheel manifest entry: $entry" >&2
      return 1
    fi

    wheel_path="${BUNDLE_DIR}/${entry}"
    decoded_entry="${entry//%2B/+}"
    decoded_entry="${decoded_entry//%2b/+}"
    escaped_entry="${entry//+/%2B}"
    link_name="$decoded_entry"

    if [[ ! -f "$wheel_path" ]]; then
      if [[ -f "${BUNDLE_DIR}/${escaped_entry}" ]]; then
        wheel_path="${BUNDLE_DIR}/${escaped_entry}"
      elif [[ -f "${BUNDLE_DIR}/${decoded_entry}" ]]; then
        wheel_path="${BUNDLE_DIR}/${decoded_entry}"
      fi
      if [[ ! -f "$wheel_path" ]]; then
        echo "Manifest wheel not found: ${BUNDLE_DIR}/${entry}, ${BUNDLE_DIR}/${escaped_entry}, or ${BUNDLE_DIR}/${decoded_entry}" >&2
        return 1
      fi
    fi

    MANIFEST_WHEELS+=("$wheel_path")
    MANIFEST_WHEEL_NAMES+=("$link_name")
  done < "$manifest"
}

prepare_manifest_find_links() {
  local i=""

  MANIFEST_LINK_WHEELS=()
  WHEEL_LINK_DIR="$(mktemp -d)"
  for i in "${!MANIFEST_WHEELS[@]}"; do
    ln -s "${MANIFEST_WHEELS[$i]}" "${WHEEL_LINK_DIR}/${MANIFEST_WHEEL_NAMES[$i]}"
    MANIFEST_LINK_WHEELS+=("${WHEEL_LINK_DIR}/${MANIFEST_WHEEL_NAMES[$i]}")
  done
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
    archive_path="${BUNDLE_DIR}/${archive}"
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

write_managed_shell_block() {
  local target_file="$1"
  local marker_begin="$2"
  local marker_end="$3"
  local block_file=""

  block_file="$(mktemp)"
  cat > "$block_file"
  python3 - "$target_file" "$marker_begin" "$marker_end" "$block_file" <<'PY'
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
marker_begin = sys.argv[2]
marker_end = sys.argv[3]
block = pathlib.Path(sys.argv[4]).read_text(encoding="utf-8")
text = target.read_text(encoding="utf-8") if target.exists() else ""

begin = text.find(marker_begin)
if begin != -1:
    end = text.find(marker_end, begin)
    if end != -1:
        end += len(marker_end)
        if end < len(text) and text[end : end + 1] == "\n":
            end += 1
        text = text[:begin] + block + text[end:]
    else:
        text = text.rstrip("\n") + "\n" + block
else:
    text = text.rstrip("\n") + "\n" + block if text else block

target.write_text(text, encoding="utf-8")
PY
  rm -f "$block_file"
}

configure_shell_path() {
  local modelsdk_dir="$1"
  local bin_dir="$2"
  local bashrc="${HOME}/.bashrc"
  local bash_profile="${HOME}/.bash_profile"
  local target_file=""
  local marker_begin="# >>> modelsdk path >>>"
  local marker_end="# <<< modelsdk path <<<"
  local functions_marker_begin="# >>> modelsdk activation >>>"
  local functions_marker_end="# <<< modelsdk activation <<<"

  if [[ -f "$bashrc" || ! -f "$bash_profile" ]]; then
    target_file="$bashrc"
  else
    target_file="$bash_profile"
  fi

  touch "$target_file"

  write_managed_shell_block "$target_file" "$marker_begin" "$marker_end" <<EOF
$marker_begin
# ModelSDK PATH is managed by activate-model-sdk and deactivate-model-sdk.
$marker_end
EOF

  if ! grep -Fq "$functions_marker_begin" "$target_file" \
    && { grep -Eq '^[[:space:]]*(function[[:space:]]+)?activate-model-sdk([[:space:]]*\(\))?[[:space:]]*\{' "$target_file" \
      || grep -Eq '^[[:space:]]*(function[[:space:]]+)?deactivate-model-sdk([[:space:]]*\(\))?[[:space:]]*\{' "$target_file"; }; then
    return 0
  fi

  write_managed_shell_block "$target_file" "$functions_marker_begin" "$functions_marker_end" <<EOF
$functions_marker_begin
_modelsdk_path_without() {
  local remove_path="\$1"
  local source_path=""
  local entry=""
  local old_ifs="\$IFS"
  local new_path=""

  if [ "\$#" -ge 2 ]; then
    source_path="\$2"
  else
    source_path="\$PATH"
  fi

  IFS=:
  for entry in \$source_path; do
    if [ -n "\$entry" ] && [ "\$entry" != "\$remove_path" ]; then
      if [ -n "\$new_path" ]; then
        new_path="\$new_path:\$entry"
      else
        new_path="\$entry"
      fi
    fi
  done
  IFS="\$old_ifs"
  printf '%s\n' "\$new_path"
}

_modelsdk_site_packages_dir() {
  find "$modelsdk_dir/lib" -maxdepth 3 -type d -name site-packages 2>/dev/null | head -n 1
}

_modelsdk_prepend_path_if_dir() {
  local dir="\$1"
  local current="\$2"
  if [ ! -d "\$dir" ]; then
    printf '%s\n' "\$current"
    return 0
  fi
  current="\$(_modelsdk_path_without "\$dir" "\$current")"
  if [ -n "\$current" ]; then
    printf '%s:%s\n' "\$dir" "\$current"
  else
    printf '%s\n' "\$dir"
  fi
}

activate-model-sdk() {
  local modelsdk_site_packages=""
  if [ ! -f "$modelsdk_dir/bin/activate" ]; then
    echo "ModelSDK virtual environment not found: $modelsdk_dir" >&2
    return 1
  fi
  PATH="\$(_modelsdk_path_without "$bin_dir")"
  . "$modelsdk_dir/bin/activate"
  PATH="\$(_modelsdk_path_without "$bin_dir")"
  if [ -n "\$PATH" ]; then
    PATH="$bin_dir:\$PATH"
  else
    PATH="$bin_dir"
  fi
  export PATH

  modelsdk_site_packages="\$(_modelsdk_site_packages_dir)"
  LD_LIBRARY_PATH="\$(_modelsdk_prepend_path_if_dir "$modelsdk_dir/lib" "\${LD_LIBRARY_PATH:-}")"
  if [ -n "\$modelsdk_site_packages" ]; then
    LD_LIBRARY_PATH="\$(_modelsdk_prepend_path_if_dir "\$modelsdk_site_packages" "\${LD_LIBRARY_PATH:-}")"
    LD_LIBRARY_PATH="\$(_modelsdk_prepend_path_if_dir "\$modelsdk_site_packages/tvm" "\${LD_LIBRARY_PATH:-}")"
    PYTHONPATH="\$(_modelsdk_prepend_path_if_dir "\$modelsdk_site_packages" "\${PYTHONPATH:-}")"
    export PYTHONPATH
  fi
  export LD_LIBRARY_PATH

  hash -r 2>/dev/null || true
}

deactivate-model-sdk() {
  local modelsdk_site_packages=""
  if [ -n "\${VIRTUAL_ENV:-}" ] && [ "\$VIRTUAL_ENV" != "$modelsdk_dir" ]; then
    echo "Active virtual environment is not ModelSDK: \$VIRTUAL_ENV" >&2
    return 1
  fi
  modelsdk_site_packages="\$(_modelsdk_site_packages_dir)"
  if command -v deactivate >/dev/null 2>&1; then
    deactivate
  fi
  PATH="\$(_modelsdk_path_without "$bin_dir")"
  export PATH

  LD_LIBRARY_PATH="\$(_modelsdk_path_without "$modelsdk_dir/lib" "\${LD_LIBRARY_PATH:-}")"
  if [ -n "\$modelsdk_site_packages" ]; then
    LD_LIBRARY_PATH="\$(_modelsdk_path_without "\$modelsdk_site_packages" "\${LD_LIBRARY_PATH:-}")"
    LD_LIBRARY_PATH="\$(_modelsdk_path_without "\$modelsdk_site_packages/tvm" "\${LD_LIBRARY_PATH:-}")"
    PYTHONPATH="\$(_modelsdk_path_without "\$modelsdk_site_packages" "\${PYTHONPATH:-}")"
    if [ -n "\$PYTHONPATH" ]; then
      export PYTHONPATH
    else
      unset PYTHONPATH
    fi
  fi
  if [ -n "\$LD_LIBRARY_PATH" ]; then
    export LD_LIBRARY_PATH
  else
    unset LD_LIBRARY_PATH
  fi

  hash -r 2>/dev/null || true
}
$functions_marker_end
EOF
}

cleanup_downloaded_resources() {
  local archive=""
  local archive_path=""
  local extracted_dir=""
  local removed=0

  while IFS= read -r archive; do
    [[ -n "$archive" ]] || continue
    archive_path="${BUNDLE_DIR}/${archive}"
    extracted_dir="${BUNDLE_DIR}/${archive%.*}"

    if [[ -f "$archive_path" ]]; then
      rm -f "$archive_path"
      removed=1
    fi
    if [[ -d "$extracted_dir" ]]; then
      rm -rf "$extracted_dir"
      removed=1
    fi
  done < <(read_source_json_field "binary_package_archives")

  if [[ -f "$WHEEL_MANIFEST" ]]; then
    for wheel in "${MANIFEST_WHEELS[@]}"; do
      [[ -n "$wheel" ]] || continue
      rm -f "$wheel"
      removed=1
    done
  fi

  if [[ "$removed" -eq 1 ]]; then
    echo "Removed downloaded bundle resources from $BUNDLE_DIR."
  else
    echo "No downloaded bundle resources needed cleanup in $BUNDLE_DIR."
  fi
}

if [[ ! -f "$SOURCE_JSON" ]]; then
  echo "Missing source.json in bundle directory: $SOURCE_JSON" >&2
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

if ! load_manifest_wheels "$WHEEL_MANIFEST"; then
  exit 1
fi
wheels=("${MANIFEST_WHEELS[@]}")
if [[ ${#wheels[@]} -eq 0 ]]; then
  echo "No wheel files listed in $WHEEL_MANIFEST" >&2
  exit 1
fi

HOST_OS_RAW="$(uname -s 2>/dev/null || echo unknown)"
HOST_OS="$(printf '%s' "$HOST_OS_RAW" | tr '[:upper:]' '[:lower:]')"
if [[ "$HOST_OS" != "linux" ]]; then
  echo "Unsupported host operating system: $HOST_OS_RAW" >&2
  echo "This ModelSDK bundle installer currently supports Linux hosts only." >&2
  echo "Detected host details: os=$HOST_OS_RAW arch=$(uname -m 2>/dev/null || echo unknown)" >&2
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
VENV_DIR="$MODELSDK_DIR"
echo "Creating virtual environment at: $VENV_DIR (python: $PYTHON_CMD, arch: $HOST_ARCH)"
"$PYTHON_CMD" -m venv "$VENV_DIR"

if ! install_binary_packages "$VENV_DIR"; then
  exit 1
fi

package_specs=()
while IFS= read -r spec; do
  [[ -n "$spec" ]] && package_specs+=("$spec")
done < <(read_source_json_field "python_package_specs")

pip_args=(
  --disable-pip-version-check
)
prepare_manifest_find_links
pip_args+=(--find-links "$WHEEL_LINK_DIR")
if [[ -n "$EXTRA_INDEX_URL" ]]; then
  pip_args+=(--extra-index-url "$EXTRA_INDEX_URL")
fi

if [[ ${#package_specs[@]} -gt 0 ]]; then
  echo "Installing ${#package_specs[@]} package spec(s) from source.json into $VENV_DIR (extras supported)"
  run_host_build_env "$VENV_DIR/bin/python" -m pip install "${pip_args[@]}" "${package_specs[@]}"
else
  echo "Installing ${#wheels[@]} wheel(s) from $BUNDLE_DIR into $VENV_DIR (with dependency resolution)"
  run_host_build_env "$VENV_DIR/bin/python" -m pip install "${pip_args[@]}" "${MANIFEST_LINK_WHEELS[@]}"
fi

configure_shell_path "$MODELSDK_DIR" "$VENV_DIR/bin"
cleanup_downloaded_resources
echo "ModelSDK wheel installation complete in $VENV_DIR."
