#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  download_modelsdk_wheels.sh \
    --index-url https://.../simple \
    --output-dir ./dist \
    [--sdk-release /path/to/sdk-release] \
    [--spec 'name==version']... \
    [--python-version 312]

Description:
  Downloads one wheel per package spec from the given Python index
  (Artifactory). Package specs can be provided with:
    - --spec 'name==version' (repeatable), or
    - --sdk-release file lines in format name==version.
  Selection priority per package:
    1) Pure-Python wheel (e.g. py3-none-any)
    2) Linux x86 wheel (manylinux/linux_x86_64)

Notes:
  - Auth should be handled by your environment/.netrc as needed.
  - Non-package lines (e.g., "SDK Version = ...") are ignored.
EOF
}

SDK_RELEASE=""
INDEX_URL=""
OUTPUT_DIR=""
PYTHON_VERSION="312"
declare -a CLI_SPECS=()
declare -a SUMMARY_REQUESTED=()
declare -a SUMMARY_RESOLVED=()
declare -a SUMMARY_WHEEL=()

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
  versions_line="$(python3 -m pip index versions "$pkg_name" --index-url "$INDEX_URL" 2>/dev/null | sed -n 's/^Available versions: //p' | head -n1)"
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
  mkdir -p "$pure_dir" "$x86_dir"

  DOWNLOADED_WHEEL=""
  DOWNLOAD_ERROR_LOG=""

  # 1) Try pure-Python wheel first.
  set +e
  python3 -m pip download \
    --disable-pip-version-check \
    --no-deps \
    --only-binary=:all: \
    --index-url "$INDEX_URL" \
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

  # 2) Fallback to x86 wheel only when pure wheel is unavailable.
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
    python3 -m pip download \
      --disable-pip-version-check \
      --no-deps \
      --only-binary=:all: \
      --index-url "$INDEX_URL" \
      --dest "$x86_try_dir" \
      --platform manylinux2014_x86_64 \
      --platform linux_x86_64 \
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
      echo "Expected exactly one x86 wheel for '$spec' (cp${pyv}), found ${#COLLECTED_WHEELS[@]}." >&2
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

download_deps_for_wheel_file() {
  local wheel_file="$1"
  local dest_dir="$2"
  local tmpdir="$3"
  local dep_log=""
  local pyv=""
  local seen_py_versions=" "

  DOWNLOAD_ERROR_LOG=""
  for pyv in "$PYTHON_VERSION" 312 311 310; do
    if [[ "$seen_py_versions" == *" $pyv "* ]]; then
      continue
    fi
    seen_py_versions="${seen_py_versions}${pyv} "
    dep_log="${tmpdir}/deps-cp${pyv}.log"

    set +e
    python3 -m pip download \
      --disable-pip-version-check \
      --only-binary=:all: \
      --index-url "$INDEX_URL" \
      --dest "$dest_dir" \
      --platform manylinux2014_x86_64 \
      --platform linux_x86_64 \
      --implementation cp \
      --abi "cp${pyv}" \
      --python-version "$pyv" \
      "$wheel_file" >"$dep_log" 2>&1
    dep_rc=$?
    set -e

    if [[ $dep_rc -eq 0 ]]; then
      return 0
    fi
  done

  if [[ -n "$dep_log" && -s "$dep_log" ]]; then
    DOWNLOAD_ERROR_LOG="$dep_log"
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
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --python-version)
      PYTHON_VERSION="${2:-}"
      shift 2
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

mkdir -p "$OUTPUT_DIR"

declare -a SPECS=()
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
  done < <(grep -E '^[[:alnum:]_.-]+(\[[^]]+\])?==[^[:space:]]+$' "$SDK_RELEASE" || true)
fi

if [[ ${#SPECS[@]} -eq 0 ]]; then
  echo "No package specs found. Provide --spec or --sdk-release." >&2
  exit 1
fi

echo "Found ${#SPECS[@]} package specs."

for requested_spec in "${SPECS[@]}"; do
  tmpdir="$(mktemp -d)"
  resolved_spec="$requested_spec"
  echo "Downloading wheel for: $requested_spec"

  if ! download_one_spec "$resolved_spec" "$tmpdir"; then
    candidate_spec="$(resolve_latest_master_spec "$requested_spec" || true)"
    if [[ -n "$candidate_spec" && "$candidate_spec" != "$requested_spec" ]]; then
      echo "  Exact version not found. Trying latest compatible master build: $candidate_spec"
      rm -rf "$tmpdir"
      tmpdir="$(mktemp -d)"
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
  mv "$DOWNLOADED_WHEEL" "$OUTPUT_DIR/"
  SUMMARY_REQUESTED+=("$requested_spec")
  SUMMARY_RESOLVED+=("$resolved_spec")
  SUMMARY_WHEEL+=("$wheel_name")
  rm -rf "$tmpdir"
done

echo "Downloaded wheels to: $OUTPUT_DIR"
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

echo "Downloading dependency wheels for resolved package set..."
dep_tmp="$(mktemp -d)"
for top_wheel in "${SUMMARY_WHEEL[@]}"; do
  wheel_path="$OUTPUT_DIR/$top_wheel"
  if [[ ! -f "$wheel_path" ]]; then
    rm -rf "$dep_tmp"
    echo "Top-level wheel missing for dependency resolution: $wheel_path" >&2
    exit 1
  fi
  echo "  Resolving deps for wheel: $top_wheel"
  if ! download_deps_for_wheel_file "$wheel_path" "$OUTPUT_DIR" "$dep_tmp"; then
    if [[ -n "${DOWNLOAD_ERROR_LOG:-}" && -f "${DOWNLOAD_ERROR_LOG:-}" ]]; then
      cat "$DOWNLOAD_ERROR_LOG" >&2
    fi
    rm -rf "$dep_tmp"
    echo "Failed to download dependencies for wheel: $top_wheel" >&2
    exit 1
  fi
done
rm -rf "$dep_tmp"

total_wheels="$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ')"
echo "Dependency bundling complete. Total wheel files in output: $total_wheels"

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
