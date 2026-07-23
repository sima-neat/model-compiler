#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  download_llima_wheel.sh --output-dir DIR [--source-json PATH]

Download the LLiMa compiler wheel with sima-cli and print its path.

Options:
  --output-dir DIR        Destination directory for the wheel (required)
  --source-json PATH      Read the LLiMa Vulcan branch from this manifest
  -h, --help              Show this help
EOF
}

OUTPUT_DIR=""
SOURCE_JSON=""
REF="develop"
SIMA_CLI_BIN="${SIMA_CLI_BIN:-sima-cli}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --source-json) SOURCE_JSON="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
  usage >&2
  exit 1
fi

if [[ -n "$SOURCE_JSON" ]]; then
  if [[ ! -f "$SOURCE_JSON" ]]; then
    echo "Source manifest not found: $SOURCE_JSON" >&2
    exit 1
  fi
  REF="$(python3 - "$SOURCE_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
doc = json.loads(path.read_text(encoding="utf-8"))
for item in doc.get("python-packages", []):
    if not isinstance(item, dict) or item.get("name") != "sima_lmm[sdk]":
        continue
    vulcan = item.get("vulcan")
    if isinstance(vulcan, dict) and isinstance(vulcan.get("branch"), str) and vulcan["branch"].strip():
        print(vulcan["branch"].strip())
        break
PY
)"
  [[ -n "$REF" ]] || exit 0
fi

if ! command -v "$SIMA_CLI_BIN" >/dev/null 2>&1; then
  echo "sima-cli is required to download llima/compiler@${REF}." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
SIMA_CLI_CHECK_FOR_UPDATE=0 "$SIMA_CLI_BIN" neat install \
  --type wheel \
  --install-dir "$OUTPUT_DIR" \
  "llima/compiler@${REF}" >&2

wheels=()
while IFS= read -r -d '' wheel; do
  wheels+=("$wheel")
done < <(
  find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'sima_lmm-*.whl' -print0
)
if [[ "${#wheels[@]}" -ne 1 ]]; then
  echo "Expected exactly one LLiMa compiler wheel in $OUTPUT_DIR; found ${#wheels[@]}." >&2
  exit 1
fi

printf '%s\n' "${wheels[0]}"
