#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  download_modelsdk_wheels.sh \
    --index-url https://.../simple \
    [--extra-index-url https://pypi.org/simple] \
    --output-dir ./dist \
    [--source-json ./scripts/source.json] \
    [--sdk-release /path/to/sdk-release] \
    [--spec 'name==version']... \
    [--spec 'name @ wheel-file.whl']... \
    [--python-version 312] \
    [--target-arch x86_64|aarch64] \
    [--include-dependencies]

Description:
  Downloads Python wheels from the configured Python index and optional
  binary packages from Artifactory. Python package specs can be provided with:
    - --spec 'name==version' or 'name @ wheel-file.whl' (repeatable), or
    - --sdk-release file lines in format name==version or name @ wheel-file.whl.
  Selection priority per package:
    1) Pure-Python wheel (e.g. py3-none-any)
    2) Linux target-architecture wheel (manylinux/linux_x86_64 or manylinux/linux_aarch64)

Notes:
  - Auth should be handled by your environment/.netrc as needed.
  - Non-package lines (e.g., "SDK Version = ...") are ignored.
EOF
}

SDK_RELEASE=""
INDEX_URL=""
EXTRA_INDEX_URL="https://pypi.org/simple"
ARTIFACTORY_BASE_URL="${ARTIFACTORY_BASE_URL:-https://artifacts.eng.sima.ai/artifactory}"
PYPI_ARTIFACTORY_BASE_URL="${PYPI_ARTIFACTORY_BASE_URL:-https://artifacts.eng.sima.ai/artifactory/sima-pypi}"
OUTPUT_DIR=""
SOURCE_JSON=""
PYTHON_VERSION="312"
TARGET_ARCH="${MODELSDK_TARGET_ARCH:-}"
INCLUDE_DEPENDENCIES="0"
declare -a CLI_SPECS=()
declare -a SUMMARY_REQUESTED=()
declare -a SUMMARY_RESOLVED=()
declare -a SUMMARY_WHEEL=()
declare -a BINARY_ARTIFACTS=()
declare -a PRELOAD_PACKAGE_SPECS=()
declare -a PRELOAD_CLOSURE_TARGETS=()
declare -a SOURCE_PACKAGE_SPECS=()
declare -a SOURCE_PACKAGE_DEP_SPECS=()
declare -a PIP_INDEX_ARGS=()
declare -a TEMP_DIRS=()
declare -a X86_PLATFORM_ARGS=(
  --platform manylinux_2_28_x86_64
  --platform manylinux_2_27_x86_64
  --platform manylinux2014_x86_64
  --platform linux_x86_64
)
declare -a AARCH64_PLATFORM_ARGS=(
  --platform manylinux_2_28_aarch64
  --platform manylinux_2_27_aarch64
  --platform manylinux2014_aarch64
  --platform linux_aarch64
)
declare -a TARGET_PLATFORM_ARGS=()

cleanup_temp_dirs() {
  local temp_dir=""
  if [[ ${#TEMP_DIRS[@]} -eq 0 ]]; then
    return 0
  fi
  for temp_dir in "${TEMP_DIRS[@]}"; do
    [[ -n "$temp_dir" ]] && rm -rf "$temp_dir"
  done
  return 0
}

register_temp_dir() {
  local temp_dir="$1"
  TEMP_DIRS+=("$temp_dir")
}

trap cleanup_temp_dirs EXIT

normalize_python_version() {
  local raw="$1"
  raw="$(echo "$raw" | tr -d '[:space:]')"
  if [[ "$raw" =~ ^[0-9]+\.[0-9]+$ ]]; then
    echo "$raw" | sed -E 's/^([0-9]+)\.([0-9]+)$/\1\2/'
    return 0
  fi
  if [[ "$raw" =~ ^[0-9]{3}$ ]]; then
    echo "$raw"
    return 0
  fi
  if [[ "$raw" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$raw" | awk -F. '{print $1$2}'
    return 0
  fi
  return 1
}

normalize_target_arch() {
  local raw="$1"
  raw="$(echo "$raw" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  case "$raw" in
    "")
      case "$(uname -m 2>/dev/null || echo unknown)" in
        x86_64|amd64) echo "x86_64" ;;
        aarch64|arm64) echo "aarch64" ;;
        *) return 1 ;;
      esac
      ;;
    x86_64|amd64) echo "x86_64" ;;
    aarch64|arm64) echo "aarch64" ;;
    *) return 1 ;;
  esac
}

resolve_python_cmd() {
  local py_mm="$1"
  local major="${py_mm%%.*}"
  local minor="${py_mm##*.}"
  local cmd=""

  if command -v "python${major}.${minor}" >/dev/null 2>&1; then
    cmd="python${major}.${minor}"
    if "$cmd" -c "import sys; raise SystemExit(0 if (sys.version_info.major, sys.version_info.minor)==(${major},${minor}) else 1)" >/dev/null 2>&1; then
      echo "$cmd"
      return 0
    fi
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

wheel_python_tag() {
  local wheel="$1"
  local base=""
  local parts=()

  base="$(basename "$wheel")"
  base="${base%.whl}"
  IFS='-' read -r -a parts <<< "$base"
  if [[ ${#parts[@]} -lt 5 ]]; then
    echo ""
    return 1
  fi
  echo "${parts[${#parts[@]}-3]}"
}

wheel_preferred_pyv() {
  local wheel="$1"
  local py_tag=""

  py_tag="$(wheel_python_tag "$wheel" 2>/dev/null || true)"
  if [[ "$py_tag" =~ ^cp([0-9]{3})$ ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi
  return 1
}

print_wheel_requirements() {
  local wheel_file="$1"
  python3 - "$wheel_file" <<'PY'
import pathlib
import sys
import zipfile

wheel = pathlib.Path(sys.argv[1])
try:
    with zipfile.ZipFile(wheel) as zf:
        meta_name = next(
            name for name in zf.namelist()
            if name.endswith(".dist-info/METADATA")
        )
        data = zf.read(meta_name).decode("utf-8", "replace").splitlines()
except Exception as exc:
    print(f"  Unable to inspect wheel metadata: {exc}", file=sys.stderr)
    raise SystemExit(0)

reqs = [line[len("Requires-Dist: "):] for line in data if line.startswith("Requires-Dist: ")]
if not reqs:
    print("  No direct Requires-Dist entries found.")
    raise SystemExit(0)

print("  Direct wheel dependencies (Requires-Dist):")
for req in reqs:
    print(f"    - {req}")
PY
}

print_dependency_failure_details() {
  local wheel_file="$1"
  local dep_log="$2"

  echo "Dependency resolution failed for wheel: $(basename "$wheel_file")" >&2
  if [[ -n "$dep_log" && -f "$dep_log" ]]; then
    echo "pip output:" >&2
    sed 's/^/  /' "$dep_log" >&2
  else
    echo "No pip log was captured for this failure." >&2
  fi

  echo "Wheel metadata summary:" >&2
  print_wheel_requirements "$wheel_file" >&2 || true
}

patch_wheel_metadata_requirements() {
  local wheel_file="$1"
  local source_json="$2"
  python3 - "$wheel_file" "$source_json" "$TARGET_ARCH" <<'PY'
import base64
import csv
import hashlib
import io
import json
import re
import pathlib
import sys
import tempfile
import zipfile

wheel = pathlib.Path(sys.argv[1])
source_json = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
target_arch = sys.argv[3] if len(sys.argv) > 3 else ""
override_map = {}
replacement_map = {}
exclusion_set = set()
if source_json and source_json.is_file():
    doc = json.loads(source_json.read_text(encoding="utf-8"))
    arch_doc = doc.get(target_arch) if target_arch else None
    if isinstance(arch_doc, dict) and isinstance(arch_doc.get("dependency_overrides"), dict):
        raw = arch_doc["dependency_overrides"]
    else:
        raw = doc.get("dependency_overrides", {})
    if isinstance(raw, dict):
        override_map = {
            str(k).strip().lower().replace("_", "-"): str(v).strip()
            for k, v in raw.items()
            if str(k).strip() and str(v).strip()
        }
    if isinstance(arch_doc, dict) and isinstance(arch_doc.get("dependency_replacements"), dict):
        raw_replacements = arch_doc["dependency_replacements"]
    else:
        raw_replacements = doc.get("dependency_replacements", {})
    if isinstance(raw_replacements, dict):
        replacement_map = {
            str(k).strip().lower().replace("_", "-"): str(v).strip()
            for k, v in raw_replacements.items()
            if str(k).strip() and str(v).strip()
        }
    if isinstance(arch_doc, dict) and isinstance(arch_doc.get("dependency_exclusions"), list):
        raw_exclusions = arch_doc["dependency_exclusions"]
    else:
        raw_exclusions = doc.get("dependency_exclusions", [])
    if isinstance(raw_exclusions, list):
        exclusion_set = {
            str(v).strip().lower().replace("_", "-")
            for v in raw_exclusions
            if str(v).strip()
        }
if not override_map:
    override_map = {}
if not override_map and not replacement_map and not exclusion_set:
    raise SystemExit(0)

tmp = tempfile.NamedTemporaryFile(prefix="patched-", suffix=".whl", dir=str(wheel.parent), delete=False)
tmp_path = pathlib.Path(tmp.name)
tmp.close()
patched = False
patched_pairs = []

try:
    with zipfile.ZipFile(wheel, "r") as zin, zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        contents = {info.filename: zin.read(info.filename) for info in zin.infolist()}
        metadata_name = next((n for n in contents if n.endswith(".dist-info/METADATA")), None)
        record_name = next((n for n in contents if n.endswith(".dist-info/RECORD")), None)
        if metadata_name is None or record_name is None:
            raise SystemExit(0)

        metadata_text = contents[metadata_name].decode("utf-8", "replace")
        req_re = re.compile(r"^(Requires-Dist:\s*)([A-Za-z0-9_.-]+)(.*)$")
        new_lines = []
        for line in metadata_text.splitlines():
            match = req_re.match(line)
            if not match:
                new_lines.append(line)
                continue
            prefix, name, remainder = match.groups()
            normalized = name.strip().lower().replace("_", "-")
            if normalized in exclusion_set:
                patched = True
                patched_pairs.append((name, remainder.strip() or "<any>", "<removed>"))
                continue
            replacement = replacement_map.get(normalized)
            if replacement:
                marker = ""
                if ";" in remainder:
                    marker = ";" + remainder.split(";", 1)[1]
                new_lines.append(f"{prefix}{replacement}{marker}")
                patched = True
                patched_pairs.append((name, remainder.strip() or "<any>", replacement))
                continue

            target = override_map.get(normalized)
            if target:
                requirement, separator, marker = remainder.partition(";")
                extras_match = re.match(r"^\s*(\[[^]]+\])", requirement)
                extras = extras_match.group(1) if extras_match else ""
                suffix = f";{marker}" if separator else ""
                replacement = f"{name}{extras} == {target}"
                new_lines.append(f"{prefix}{replacement}{suffix}")
                patched = True
                patched_pairs.append((name, remainder.strip() or "<any>", replacement))
            else:
                new_lines.append(line)
        if patched:
            contents[metadata_name] = ("\n".join(new_lines) + "\n").encode("utf-8")

        if patched:
            rows = []
            for row in csv.reader(io.StringIO(contents[record_name].decode("utf-8", "replace"))):
                if not row:
                    continue
                path = row[0]
                if path == record_name:
                    rows.append([path, "", ""])
                    continue
                data = contents[path]
                digest = hashlib.sha256(data).digest()
                encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
                rows.append([path, f"sha256={encoded}", str(len(data))])
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            writer.writerows(rows)
            contents[record_name] = out.getvalue().encode("utf-8")

        for info in zin.infolist():
            zinfo = zipfile.ZipInfo(info.filename)
            zinfo.date_time = info.date_time
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.comment = info.comment
            zinfo.extra = info.extra
            zinfo.create_system = info.create_system
            zinfo.external_attr = info.external_attr
            zinfo.internal_attr = info.internal_attr
            zinfo.flag_bits = info.flag_bits
            zout.writestr(zinfo, contents[info.filename])

    if patched:
        tmp_path.replace(wheel)
        for name, old, new in patched_pairs:
            print(f"  Patched {wheel.name}: {name} {old} -> {new}", file=sys.stderr)
    else:
        tmp_path.unlink(missing_ok=True)
except Exception:
    tmp_path.unlink(missing_ok=True)
    raise
PY
}

extract_direct_internal_specs() {
  local wheel_file="$1"
  python3 - "$wheel_file" <<'PY'
import pathlib
import sys
import zipfile

wheel = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(wheel) as zf:
    meta_name = next(
        name for name in zf.namelist()
        if name.endswith(".dist-info/METADATA")
    )
    data = zf.read(meta_name).decode("utf-8", "replace").splitlines()

for line in data:
    if not line.startswith("Requires-Dist: "):
        continue
    req = line[len("Requires-Dist: "):]
    if 'extra == "' in req:
        continue
    req = req.split(";", 1)[0].strip()
    if not req or "==" not in req:
        continue
    name = req.split("==", 1)[0].strip().lower().replace("_", "-")
    if name.startswith("sima-") or name == "mpk-parser":
        print(req)
PY
}

read_binary_package_specs() {
  local source_json="$1"
  [[ -n "$source_json" && -f "$source_json" ]] || return 0
  python3 - "$source_json" "$TARGET_ARCH" <<'PY'
import json
import pathlib
import sys

doc = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
target_arch = sys.argv[2] if len(sys.argv) > 2 else ""
arch_doc = doc.get(target_arch) if target_arch else None
if isinstance(arch_doc, dict) and isinstance(arch_doc.get("binary-packages"), list):
    items = arch_doc["binary-packages"]
else:
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
        normalized = name.lower().strip("/")
        if archive_type == "zip" and normalized.endswith("mla-toolchain") and "mla" in normalized:
            arch_suffix = {"x86_64": "x86", "aarch64": "aarch64"}.get(target_arch)
            if not arch_suffix:
                raise SystemExit(f"unsupported MLA toolchain architecture: {target_arch!r}")
            version = f"{version}-{arch_suffix}-ubuntu"
        print(f"{name}|{version}|{archive_type}")
PY
}

read_source_package_specs() {
  local source_json="$1"
  [[ -n "$source_json" && -f "$source_json" ]] || return 0
  python3 - "$source_json" "$TARGET_ARCH" <<'PY'
import json
import pathlib
import sys

doc = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
target_arch = sys.argv[2] if len(sys.argv) > 2 else ""
arch_doc = doc.get(target_arch) if target_arch else None
if isinstance(arch_doc, dict) and isinstance(arch_doc.get("source-packages"), list):
    items = arch_doc["source-packages"]
else:
    items = doc.get("source-packages", [])
if not isinstance(items, list):
    raise SystemExit(0)
seen_deps = set()
for item in items:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name", "")).strip()
    version = str(item.get("version", "")).strip()
    if name and version:
        print(f"package|{name}=={version}")
    for key in ("build-dependencies", "dependencies"):
        deps = item.get(key, [])
        if not isinstance(deps, list):
            continue
        for dep in deps:
            dep = str(dep).strip()
            if dep and dep not in seen_deps:
                seen_deps.add(dep)
                print(f"dependency|{dep}")
PY
}

read_preload_package_specs() {
  local source_json="$1"
  [[ -n "$source_json" && -f "$source_json" ]] || return 0
  python3 - "$source_json" "$TARGET_ARCH" <<'PY'
import json
import pathlib
import sys

doc = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
target_arch = sys.argv[2] if len(sys.argv) > 2 else ""
arch_doc = doc.get(target_arch) if target_arch else None
if isinstance(arch_doc, dict) and isinstance(arch_doc.get("preload-packages"), list):
    items = arch_doc["preload-packages"]
else:
    items = doc.get("preload-packages", [])
if not isinstance(items, list):
    raise SystemExit(0)
for item in items:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name", "")).strip()
    version = str(item.get("version", "")).strip()
    if name and version:
        print(f"{name}=={version}")
PY
}

is_mla_toolchain_package() {
  local package_name="$1"
  local archive_type="${2:-zip}"
  local normalized=""
  local leaf=""

  normalized="$(echo "$package_name" | tr '[:upper:]' '[:lower:]' | sed -E 's#^/+|/+$##g')"
  leaf="$(basename "$normalized")"
  [[ "$archive_type" == "zip" && "$leaf" == "mla-toolchain" && "$normalized" == *mla*toolchain* ]]
}

sanitize_mla_toolchain_zip() {
  local archive_path="$1"
  local tmp_path=""

  tmp_path="$(mktemp "${archive_path}.sanitized.XXXXXX")"
  rm -f "$tmp_path"

  python3 - "$archive_path" "$tmp_path" <<'PY'
import pathlib
import shutil
import sys
import zipfile

source = pathlib.Path(sys.argv[1])
dest = pathlib.Path(sys.argv[2])
kept = 0

try:
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(dest, "w") as zout:
        for info in zin.infolist():
            parts = pathlib.PurePosixPath(info.filename).parts
            if "bin" not in parts:
                continue

            copied = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            copied.compress_type = info.compress_type
            copied.comment = info.comment
            copied.extra = info.extra
            copied.internal_attr = info.internal_attr
            copied.external_attr = info.external_attr
            copied.create_system = info.create_system

            if info.is_dir():
                zout.writestr(copied, b"")
            else:
                with zin.open(info, "r") as src:
                    with zout.open(copied, "w") as dst:
                        shutil.copyfileobj(src, dst)
                kept += 1
except Exception:
    dest.unlink(missing_ok=True)
    raise

if kept == 0:
    dest.unlink(missing_ok=True)
    raise SystemExit(f"No bin files found in MLA toolchain archive: {source.name}")
PY

  mv "$tmp_path" "$archive_path"
}

download_binary_package() {
  local package_name="$1"
  local package_version="$2"
  local archive_type="${3:-zip}"
  local artifact_rel=""
  local artifact_name=""
  local url=""
  local out_path=""
  local tmp_path=""

  artifact_rel="${package_name}-${package_version}.${archive_type}"
  artifact_name="$(basename "$artifact_rel")"
  url="${ARTIFACTORY_BASE_URL}/${artifact_rel}"
  out_path="${OUTPUT_DIR}/${artifact_name}"

  if [[ -f "$out_path" ]]; then
    if is_mla_toolchain_package "$package_name" "$archive_type"; then
      sanitize_mla_toolchain_zip "$out_path"
    fi
    BINARY_ARTIFACTS+=("$artifact_name")
    return 0
  fi

  tmp_path="$(mktemp "${OUTPUT_DIR}/.${artifact_name}.XXXXXX")"
  rm -f "$tmp_path"

  if command -v curl >/dev/null 2>&1; then
    if ! curl -fsSL --netrc-optional -o "$tmp_path" "$url"; then
      rm -f "$tmp_path"
      echo "Failed to download binary package: ${package_name} (${package_version})" >&2
      echo "URL: $url" >&2
      return 1
    fi
  elif command -v wget >/dev/null 2>&1; then
    if ! wget --quiet -O "$tmp_path" "$url"; then
      rm -f "$tmp_path"
      echo "Failed to download binary package: ${package_name} (${package_version})" >&2
      echo "URL: $url" >&2
      return 1
    fi
  else
    echo "curl or wget is required to download binary packages." >&2
    return 1
  fi

  mv "$tmp_path" "$out_path"
  if is_mla_toolchain_package "$package_name" "$archive_type"; then
    sanitize_mla_toolchain_zip "$out_path"
  fi
  BINARY_ARTIFACTS+=("$artifact_name")
  return 0
}

download_source_packages() {
  local spec=""
  local dep=""
  local dep_dir=""
  local dep_log=""

  if [[ ${#SOURCE_PACKAGE_SPECS[@]} -eq 0 ]]; then
    return 0
  fi

  echo "Downloading ${#SOURCE_PACKAGE_SPECS[@]} source package(s) for bundled source builds..."
  for spec in "${SOURCE_PACKAGE_SPECS[@]}"; do
    PIP_NO_INPUT=1 python3 -m pip download \
      --disable-pip-version-check \
      --no-deps \
      --no-binary=:all: \
      "${PIP_INDEX_ARGS[@]}" \
      --dest "$OUTPUT_DIR" \
      "$spec"
  done

  if [[ ${#SOURCE_PACKAGE_DEP_SPECS[@]} -eq 0 ]]; then
    return 0
  fi

  dep_dir="$(mktemp -d)"
  register_temp_dir "$dep_dir"
  dep_log="${dep_dir}/source-package-dependencies.log"
  echo "Downloading source package build/runtime dependency wheels..."
  set +e
  PIP_NO_INPUT=1 python3 -m pip download \
    --disable-pip-version-check \
    --only-binary=:all: \
    "${PIP_INDEX_ARGS[@]}" \
    --find-links "$OUTPUT_DIR" \
    --dest "$OUTPUT_DIR" \
    "${TARGET_PLATFORM_ARGS[@]}" \
    --implementation cp \
    --abi "cp${PYTHON_VERSION}" \
    --python-version "$PYTHON_VERSION" \
    "${SOURCE_PACKAGE_DEP_SPECS[@]}" >"$dep_log" 2>&1
  dep_rc=$?
  set -e
  if [[ $dep_rc -ne 0 ]]; then
    cat "$dep_log" >&2
    echo "Failed to download source package dependency wheels." >&2
    return 1
  fi
  sed 's/^/  /' "$dep_log"
  return 0
}

download_preload_packages() {
  local spec=""
  local tmpdir=""
  local wheel_name=""
  local package_spec=""
  local wheel_path=""

  if [[ ${#PRELOAD_PACKAGE_SPECS[@]} -eq 0 ]]; then
    return 0
  fi

  echo "Preloading ${#PRELOAD_PACKAGE_SPECS[@]} resolver helper wheel(s)..."
  for spec in "${PRELOAD_PACKAGE_SPECS[@]}"; do
    tmpdir="$(mktemp -d)"
    register_temp_dir "$tmpdir"
    echo "  Preloading wheel for: $spec"
    if ! download_one_spec "$spec" "$tmpdir"; then
      if [[ -n "${DOWNLOAD_ERROR_LOG:-}" && -f "${DOWNLOAD_ERROR_LOG:-}" ]]; then
        cat "$DOWNLOAD_ERROR_LOG" >&2
      fi
      rm -rf "$tmpdir"
      echo "Failed to preload package: $spec" >&2
      return 1
    fi

    wheel_name="$(basename "$DOWNLOADED_WHEEL")"
    patch_wheel_metadata_requirements "$DOWNLOADED_WHEEL" "$SOURCE_JSON"
    mv -f "$DOWNLOADED_WHEEL" "$OUTPUT_DIR/"
    wheel_path="$OUTPUT_DIR/$wheel_name"

    if [[ "$spec" == *"=="* ]]; then
      package_spec="${spec%%==*}"
    else
      package_spec=""
    fi
    package_spec="${package_spec#"${package_spec%%[![:space:]]*}"}"
    package_spec="${package_spec%"${package_spec##*[![:space:]]}"}"
    if [[ "$package_spec" == *"["*"]"* ]]; then
      PRELOAD_CLOSURE_TARGETS+=("${package_spec} @ $(file_uri "$wheel_path")")
    else
      PRELOAD_CLOSURE_TARGETS+=("$wheel_path")
    fi
    rm -rf "$tmpdir"
  done
}

download_direct_internal_deps_for_wheel() {
  local wheel_file="$1"
  local dest_dir="$2"
  local tmpdir="$3"
  local dep_spec=""
  local dep_tmp=""
  local dep_wheel=""
  local dep_specs=()

  while IFS= read -r dep_spec; do
    [[ -n "$dep_spec" ]] && dep_specs+=("$dep_spec")
  done < <(extract_direct_internal_specs "$wheel_file")

  if [[ ${#dep_specs[@]} -eq 0 ]]; then
    return 0
  fi

  for dep_spec in "${dep_specs[@]}"; do
    dep_tmp="$(mktemp -d "${tmpdir}/dep.XXXXXX")"
    register_temp_dir "$dep_tmp"
    if ! download_one_spec "$dep_spec" "$dep_tmp"; then
      if [[ -n "${DOWNLOAD_ERROR_LOG:-}" && -f "${DOWNLOAD_ERROR_LOG:-}" ]]; then
        cat "$DOWNLOAD_ERROR_LOG" >&2
      fi
      rm -rf "$dep_tmp"
      echo "Failed to download direct internal dependency: $dep_spec" >&2
      return 1
    fi
    dep_wheel="$(basename "$DOWNLOADED_WHEEL")"
    patch_wheel_metadata_requirements "$DOWNLOADED_WHEEL" "$SOURCE_JSON"
    mv -f "$DOWNLOADED_WHEEL" "$dest_dir/"
    rm -rf "$dep_tmp"
  done

  return 0
}

file_uri() {
  python3 - "$1" <<'PY'
import pathlib
import sys

print(pathlib.Path(sys.argv[1]).resolve().as_uri())
PY
}

closure_target_for_summary_entry() {
  local spec="$1"
  local wheel_name="$2"
  local package_spec=""
  local wheel_path="${OUTPUT_DIR}/${wheel_name}"

  if [[ ! -f "$wheel_path" ]]; then
    echo "Top-level wheel missing for dependency closure: $wheel_path" >&2
    return 1
  fi

  if [[ "$spec" == *" @ "* ]]; then
    package_spec="${spec%% @ *}"
  elif [[ "$spec" == *"=="* ]]; then
    package_spec="${spec%%==*}"
  else
    package_spec=""
  fi

  package_spec="${package_spec#"${package_spec%%[![:space:]]*}"}"
  package_spec="${package_spec%"${package_spec##*[![:space:]]}"}"

  if [[ "$package_spec" == *"["*"]"* ]]; then
    printf '%s @ %s\n' "$package_spec" "$(file_uri "$wheel_path")"
  else
    printf '%s\n' "$wheel_path"
  fi
}

download_full_dependency_closure() {
  local dep_dir=""
  local dep_log=""
  local spec=""
  local wheel=""
  local wheel_path=""
  local i=0
  local -a closure_targets=()
  local -a summary_target_wheels=()
  local -a wheels=()

  while [[ $i -lt ${#SUMMARY_RESOLVED[@]} ]]; do
    spec="${SUMMARY_RESOLVED[$i]}"
    wheel="${SUMMARY_WHEEL[$i]}"
    if [[ -n "$spec" && -n "$wheel" ]]; then
      closure_targets+=("$(closure_target_for_summary_entry "$spec" "$wheel")")
      summary_target_wheels+=("$wheel")
    fi
    i=$((i + 1))
  done

  while IFS= read -r wheel_path; do
    [[ -n "$wheel_path" ]] || continue
    wheel="$(basename "$wheel_path")"
    if [[ " ${summary_target_wheels[*]} " == *" ${wheel} "* ]]; then
      continue
    fi
    wheels+=("$wheel_path")
  done < <(find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.whl' | sort)

  if [[ ${#wheels[@]} -gt 0 ]]; then
    closure_targets+=("${wheels[@]}")
  fi
  if [[ ${#PRELOAD_CLOSURE_TARGETS[@]} -gt 0 ]]; then
    closure_targets+=("${PRELOAD_CLOSURE_TARGETS[@]}")
  fi

  if [[ ${#closure_targets[@]} -eq 0 ]]; then
    echo "No package specs or wheels found for dependency closure." >&2
    return 1
  fi

  dep_dir="$(mktemp -d)"
  register_temp_dir "$dep_dir"
  dep_log="${dep_dir}/pip-download-dependencies.log"

  echo "Downloading full dependency closure for package bundle..."
  echo "  Resolving from local patched wheels; package extras are preserved with direct references."
  set +e
  PIP_NO_INPUT=1 python3 -m pip download \
    --disable-pip-version-check \
    --only-binary=:all: \
    "${PIP_INDEX_ARGS[@]}" \
    --find-links "$OUTPUT_DIR" \
    --dest "$OUTPUT_DIR" \
    "${TARGET_PLATFORM_ARGS[@]}" \
    --implementation cp \
    --abi "cp${PYTHON_VERSION}" \
    --python-version "$PYTHON_VERSION" \
    "${closure_targets[@]}" >"$dep_log" 2>&1
  dep_rc=$?
  set -e

  if [[ $dep_rc -ne 0 ]]; then
    cat "$dep_log" >&2
    echo "Failed to download full dependency closure for package bundle." >&2
    return 1
  fi

  sed 's/^/  /' "$dep_log"
  return 0
}

collect_wheels() {
  local dir="$1"
  COLLECTED_WHEELS=()
  local wheel=""
  while IFS= read -r wheel; do
    [[ -n "$wheel" ]] && COLLECTED_WHEELS+=("$wheel")
  done < <(find "$dir" -maxdepth 1 -type f -name '*.whl' | sort)
}

resolve_latest_master_spec() {
  local requested_spec="$1"
  local pkg_spec="${requested_spec%%==*}"
  local requested_ver="${requested_spec#*==}"
  local pkg_name="${pkg_spec%%[*}"

  if [[ "$pkg_spec" == "$requested_spec" ]]; then
    return 1
  fi

  # Example: 2.0.0.dev0+master.371 -> base 2.0.0
  if [[ ! "$requested_ver" =~ ^([0-9]+\.[0-9]+\.[0-9]+).*\+master\.[0-9]+$ ]]; then
    return 1
  fi
  local version_base="${BASH_REMATCH[1]}"
  local escaped_base="${version_base//./\\.}"

  local versions_line=""
  versions_line="$(PIP_NO_INPUT=1 python3 -m pip index versions "$pkg_name" "${PIP_INDEX_ARGS[@]}" 2>/dev/null | sed -n 's/^Available versions: //p' | head -n1)"
  if [[ -z "$versions_line" ]]; then
    return 1
  fi

  local best=""
  best="$(
    echo "$versions_line" \
      | tr ',' '\n' \
      | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
      | grep -E "^${escaped_base}\.dev[0-9]+\+master\.[0-9]+$" \
      | awk -F'\\+master\\.' '{print $2" "$0}' \
      | sort -n \
      | tail -n1 \
      | sed 's/^[0-9][0-9]* //'
  )"
  if [[ -z "$best" ]]; then
    return 1
  fi

  echo "${pkg_spec}==${best}"
  return 0
}

download_one_spec() {
  local spec="$1"
  local tmpdir="$2"
  local pure_dir="${tmpdir}/pure"
  local x86_dir="${tmpdir}/x86"
  local pure_log="${tmpdir}/pure.log"
  local x86_log="${tmpdir}/x86.log"
  local x86_try_dir=""
  local pyv=""
  local seen_py_versions=" "
  local direct_package=""
  local direct_ref=""
  local direct_url=""
  local direct_name=""
  local direct_path=""
  mkdir -p "$pure_dir" "$x86_dir"

  DOWNLOADED_WHEEL=""
  DOWNLOAD_ERROR_LOG=""

  if [[ "$spec" == *" @ "* ]]; then
    direct_package="${spec%% @ *}"
    direct_package="${direct_package%%[*}"
    direct_package="${direct_package//_/-}"
    direct_ref="${spec#* @ }"
    if [[ "$direct_ref" == http://* || "$direct_ref" == https://* ]]; then
      direct_url="$direct_ref"
    elif [[ "$direct_ref" == *.whl && "$direct_ref" != */* ]]; then
      direct_url="${PYPI_ARTIFACTORY_BASE_URL%/}/${direct_package}/${direct_ref}"
    elif [[ "$direct_ref" == *.whl ]]; then
      direct_url="${PYPI_ARTIFACTORY_BASE_URL%/}/${direct_ref#/}"
    fi
  elif [[ "$spec" == http://* || "$spec" == https://* ]]; then
    direct_url="$spec"
  fi

  if [[ -n "$direct_url" ]]; then
    direct_name="${direct_url%%\?*}"
    direct_name="${direct_name##*/}"
    if [[ -z "$direct_name" || "$direct_name" != *.whl ]]; then
      echo "Direct package URL must point to a .whl file: $direct_url" >&2
      return 1
    fi
    direct_path="${tmpdir}/${direct_name}"
    if command -v curl >/dev/null 2>&1; then
      if ! curl -fsSL --netrc-optional -o "$direct_path" "$direct_url"; then
        rm -f "$direct_path"
        echo "Failed to download direct wheel URL: $direct_url" >&2
        return 1
      fi
    elif command -v wget >/dev/null 2>&1; then
      if ! wget --quiet -O "$direct_path" "$direct_url"; then
        rm -f "$direct_path"
        echo "Failed to download direct wheel URL: $direct_url" >&2
        return 1
      fi
    else
      echo "curl or wget is required to download direct wheel URLs." >&2
      return 1
    fi
    DOWNLOADED_WHEEL="$direct_path"
    return 0
  fi

  # 1) Try pure-Python wheel first.
  set +e
  PIP_NO_INPUT=1 python3 -m pip download \
    --disable-pip-version-check \
    --verbose \
    --verbose \
    --no-deps \
    --only-binary=:all: \
    "${PIP_INDEX_ARGS[@]}" \
    --dest "$pure_dir" \
    --platform any \
    --implementation py \
    --abi none \
    --python-version 3 \
    "$spec" >"$pure_log" 2>&1
  pure_rc=$?
  set -e

  collect_wheels "$pure_dir"
  if [[ $pure_rc -eq 0 && ${#COLLECTED_WHEELS[@]} -eq 1 ]]; then
    DOWNLOADED_WHEEL="${COLLECTED_WHEELS[0]}"
    return 0
  fi
  if [[ ${#COLLECTED_WHEELS[@]} -gt 1 ]]; then
    echo "Expected exactly one pure wheel for '$spec', found ${#COLLECTED_WHEELS[@]}." >&2
    return 1
  fi

  # 2) Fallback to a target-architecture wheel only when a pure wheel is unavailable.
  # Try requested python ABI first, then common alternatives.
  for pyv in "$PYTHON_VERSION" 312 311 310; do
    if [[ "$seen_py_versions" == *" $pyv "* ]]; then
      continue
    fi
    seen_py_versions="${seen_py_versions}${pyv} "

    x86_try_dir="${x86_dir}/cp${pyv}"
    mkdir -p "$x86_try_dir"
    x86_log="${tmpdir}/x86-cp${pyv}.log"

    set +e
    PIP_NO_INPUT=1 python3 -m pip download \
      --disable-pip-version-check \
      --verbose \
      --verbose \
      --no-deps \
      --only-binary=:all: \
      "${PIP_INDEX_ARGS[@]}" \
      --dest "$x86_try_dir" \
      "${TARGET_PLATFORM_ARGS[@]}" \
      --implementation cp \
      --abi "cp${pyv}" \
      --python-version "$pyv" \
      "$spec" >"$x86_log" 2>&1
    x86_rc=$?
    set -e

    collect_wheels "$x86_try_dir"
    if [[ $x86_rc -eq 0 && ${#COLLECTED_WHEELS[@]} -eq 1 ]]; then
      DOWNLOADED_WHEEL="${COLLECTED_WHEELS[0]}"
      return 0
    fi
    if [[ ${#COLLECTED_WHEELS[@]} -gt 1 ]]; then
      echo "Expected exactly one ${TARGET_ARCH} wheel for '$spec' (cp${pyv}), found ${#COLLECTED_WHEELS[@]}." >&2
      return 1
    fi
  done

  if [[ -s "$x86_log" ]]; then
    DOWNLOAD_ERROR_LOG="$x86_log"
  elif [[ -s "$pure_log" ]]; then
    DOWNLOAD_ERROR_LOG="$pure_log"
  fi
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sdk-release)
      SDK_RELEASE="${2:-}"
      shift 2
      ;;
    --spec)
      CLI_SPECS+=("${2:-}")
      shift 2
      ;;
    --index-url)
      INDEX_URL="${2:-}"
      shift 2
      ;;
    --extra-index-url)
      EXTRA_INDEX_URL="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --source-json)
      SOURCE_JSON="${2:-}"
      shift 2
      ;;
    --python-version)
      PYTHON_VERSION="${2:-}"
      shift 2
      ;;
    --target-arch)
      TARGET_ARCH="${2:-}"
      shift 2
      ;;
    --include-dependencies)
      INCLUDE_DEPENDENCIES="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$INDEX_URL" || -z "$OUTPUT_DIR" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 1
fi

if ! PYTHON_VERSION="$(normalize_python_version "$PYTHON_VERSION")"; then
  echo "Unsupported python version for wheel selection: '$PYTHON_VERSION'" >&2
  exit 1
fi

if ! TARGET_ARCH="$(normalize_target_arch "$TARGET_ARCH")"; then
  echo "Unsupported target architecture for wheel selection: '${TARGET_ARCH:-}'" >&2
  exit 1
fi
case "$TARGET_ARCH" in
  x86_64) TARGET_PLATFORM_ARGS=("${X86_PLATFORM_ARGS[@]}") ;;
  aarch64) TARGET_PLATFORM_ARGS=("${AARCH64_PLATFORM_ARGS[@]}") ;;
  *)
    echo "Unsupported target architecture for wheel selection: '$TARGET_ARCH'" >&2
    exit 1
    ;;
esac
echo "Using target architecture for wheel selection: $TARGET_ARCH"

PIP_INDEX_ARGS=(--index-url "$INDEX_URL")
if [[ -n "$EXTRA_INDEX_URL" ]]; then
  PIP_INDEX_ARGS+=(--extra-index-url "$EXTRA_INDEX_URL")
fi

mkdir -p "$OUTPUT_DIR"

declare -a SPECS=()
declare -a BINARY_SPECS=()
if [[ ${#CLI_SPECS[@]} -gt 0 ]]; then
  for s in "${CLI_SPECS[@]}"; do
    SPECS+=("$s")
  done
fi

if [[ -n "$SDK_RELEASE" ]]; then
  if [[ ! -f "$SDK_RELEASE" ]]; then
    echo "sdk-release file not found: $SDK_RELEASE" >&2
    exit 1
  fi
  while IFS= read -r line; do
    [[ -n "$line" ]] && SPECS+=("$line")
  done < <(
    awk '
      /^[[:space:]]*#/ { next }
      {
        line=$0
        sub(/^[[:space:]]+/, "", line)
        sub(/[[:space:]]+$/, "", line)
        if (line ~ /^[[:alnum:]_.-]+(\[[^]]+\])?==[^[:space:]]+$/ || line ~ /^[[:alnum:]_.-]+(\[[^]]+\])?[[:space:]]+@[[:space:]]+[^[:space:]]+\.whl$/) {
          print line
        }
      }
    ' "$SDK_RELEASE"
  )
fi

if [[ -n "$SOURCE_JSON" && -f "$SOURCE_JSON" ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && BINARY_SPECS+=("$line")
  done < <(read_binary_package_specs "$SOURCE_JSON")
  while IFS='|' read -r kind value; do
    [[ -n "$kind" && -n "$value" ]] || continue
    case "$kind" in
      package) SOURCE_PACKAGE_SPECS+=("$value") ;;
      dependency) SOURCE_PACKAGE_DEP_SPECS+=("$value") ;;
    esac
  done < <(read_source_package_specs "$SOURCE_JSON")
  while IFS= read -r line; do
    [[ -n "$line" ]] && PRELOAD_PACKAGE_SPECS+=("$line")
  done < <(read_preload_package_specs "$SOURCE_JSON")
fi

if [[ ${#SPECS[@]} -eq 0 && ${#BINARY_SPECS[@]} -eq 0 ]]; then
  echo "No package specs found. Provide --spec, --sdk-release, or binary-packages in source.json." >&2
  exit 1
fi

echo "Found ${#SPECS[@]} python package spec(s)."

if [[ ${#SPECS[@]} -gt 0 ]]; then
  for requested_spec in "${SPECS[@]}"; do
    tmpdir="$(mktemp -d)"
    register_temp_dir "$tmpdir"
    resolved_spec="$requested_spec"
    echo "Downloading wheel for: $requested_spec"

    if ! download_one_spec "$resolved_spec" "$tmpdir"; then
      candidate_spec="$(resolve_latest_master_spec "$requested_spec" || true)"
      if [[ -n "$candidate_spec" && "$candidate_spec" != "$requested_spec" ]]; then
        echo "  Exact version not found. Trying latest compatible master build: $candidate_spec"
        rm -rf "$tmpdir"
        tmpdir="$(mktemp -d)"
        register_temp_dir "$tmpdir"
        if download_one_spec "$candidate_spec" "$tmpdir"; then
          resolved_spec="$candidate_spec"
        else
          if [[ -n "${DOWNLOAD_ERROR_LOG:-}" && -f "${DOWNLOAD_ERROR_LOG:-}" ]]; then
            cat "$DOWNLOAD_ERROR_LOG" >&2
          fi
          rm -rf "$tmpdir"
          echo "Failed to download package: $requested_spec" >&2
          exit 1
        fi
      else
        if [[ -n "${DOWNLOAD_ERROR_LOG:-}" && -f "${DOWNLOAD_ERROR_LOG:-}" ]]; then
          cat "$DOWNLOAD_ERROR_LOG" >&2
        fi
        rm -rf "$tmpdir"
        echo "Failed to download package: $requested_spec" >&2
        exit 1
      fi
    fi

    wheel_name="$(basename "$DOWNLOADED_WHEEL")"
    patch_wheel_metadata_requirements "$DOWNLOADED_WHEEL" "$SOURCE_JSON"
    mv "$DOWNLOADED_WHEEL" "$OUTPUT_DIR/"
    SUMMARY_REQUESTED+=("$requested_spec")
    SUMMARY_RESOLVED+=("$resolved_spec")
    SUMMARY_WHEEL+=("$wheel_name")
    rm -rf "$tmpdir"
  done
fi

if [[ ${#BINARY_SPECS[@]} -gt 0 ]]; then
  echo "Downloading ${#BINARY_SPECS[@]} binary package(s)..."
  for binary_spec in "${BINARY_SPECS[@]}"; do
    IFS='|' read -r binary_name binary_version binary_type <<< "$binary_spec"
    echo "Downloading binary package for: ${binary_name}==${binary_version}"
    if ! download_binary_package "$binary_name" "$binary_version" "$binary_type"; then
      exit 1
    fi
  done
fi

echo "Downloaded bundle artifacts to: $OUTPUT_DIR"
echo "Summary:"

repeat_char() {
  local n="$1"
  local ch="$2"
  local s=""
  while [[ ${#s} -lt "$n" ]]; do
    s="${s}${ch}"
  done
  printf '%s' "$s"
}

ok_w=4
req_w=9
res_w=8
wheel_w=5

i=0
while [[ $i -lt ${#SUMMARY_REQUESTED[@]} ]]; do
  cur_req="${SUMMARY_REQUESTED[$i]}"
  cur_res="${SUMMARY_RESOLVED[$i]}"
  cur_wheel="${SUMMARY_WHEEL[$i]}"
  if [[ ${#cur_req} -gt $req_w ]]; then req_w=${#cur_req}; fi
  if [[ ${#cur_res} -gt $res_w ]]; then res_w=${#cur_res}; fi
  if [[ ${#cur_wheel} -gt $wheel_w ]]; then wheel_w=${#cur_wheel}; fi
  i=$((i + 1))
done

if [[ ${#SUMMARY_WHEEL[@]} -gt 0 ]]; then
  echo "Downloading direct internal dependency wheels for resolved package set..."
  dep_tmp="$(mktemp -d)"
  register_temp_dir "$dep_tmp"
  for top_wheel in "${SUMMARY_WHEEL[@]}"; do
    wheel_path="$OUTPUT_DIR/$top_wheel"
    if [[ ! -f "$wheel_path" ]]; then
      rm -rf "$dep_tmp"
      echo "Top-level wheel missing for dependency bundling: $wheel_path" >&2
      exit 1
    fi
    echo "  Collecting direct internal deps for wheel: $top_wheel"
    if ! download_direct_internal_deps_for_wheel "$wheel_path" "$OUTPUT_DIR" "$dep_tmp"; then
      rm -rf "$dep_tmp"
      echo "Failed to download direct internal dependencies for wheel: $top_wheel" >&2
      exit 1
    fi
  done
  rm -rf "$dep_tmp"
fi

if [[ "$INCLUDE_DEPENDENCIES" == "1" ]]; then
  download_preload_packages
  download_full_dependency_closure
  download_source_packages
fi

total_wheels="$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ')"
total_binary="$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.zip' | wc -l | tr -d ' ')"
echo "Direct internal dependency bundling complete. Total wheel files in output: $total_wheels"
echo "Binary artifacts in output: $total_binary"

row_fmt="%-${ok_w}s | %-${req_w}s | %-${res_w}s | %-${wheel_w}s\n"
printf "$row_fmt" "OK" "Requested" "Resolved" "Wheel"
printf '%s-+-%s-+-%s-+-%s\n' \
  "$(repeat_char "$ok_w" "-")" \
  "$(repeat_char "$req_w" "-")" \
  "$(repeat_char "$res_w" "-")" \
  "$(repeat_char "$wheel_w" "-")"

i=0
while [[ $i -lt ${#SUMMARY_REQUESTED[@]} ]]; do
  ok="  ✗"
  if [[ "${SUMMARY_REQUESTED[$i]}" == "${SUMMARY_RESOLVED[$i]}" ]]; then
    ok="  ✓"
  fi
  printf "$row_fmt" \
    "$ok" \
    "${SUMMARY_REQUESTED[$i]}" \
    "${SUMMARY_RESOLVED[$i]}" \
    "${SUMMARY_WHEEL[$i]}"
  i=$((i + 1))
done
