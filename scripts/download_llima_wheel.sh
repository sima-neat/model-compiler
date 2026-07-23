#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  download_llima_wheel.sh --output-dir DIR [--source-json PATH --target-arch ARCH]

Download the LLiMa compiler wheel with sima-cli and print its path.

Options:
  --output-dir DIR        Destination directory for the wheel (required)
  --source-json PATH      Read the LLiMa Vulcan ref from this manifest
  --target-arch ARCH      Target architecture used to select manifest overrides
  -h, --help              Show this help
EOF
}

OUTPUT_DIR=""
SOURCE_JSON=""
TARGET_ARCH=""
REF="develop"
SIMA_CLI_BIN="${SIMA_CLI_BIN:-sima-cli}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --source-json) SOURCE_JSON="${2:-}"; shift 2 ;;
    --target-arch) TARGET_ARCH="${2:-}"; shift 2 ;;
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
  case "$TARGET_ARCH" in
    x86_64|amd64) TARGET_ARCH="x86_64" ;;
    aarch64|arm64) TARGET_ARCH="aarch64" ;;
    *)
      echo "A supported --target-arch is required with --source-json: ${TARGET_ARCH:-<empty>}" >&2
      exit 1
      ;;
  esac
  REF="$(python3 - "$SOURCE_JSON" "$TARGET_ARCH" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
target_arch = sys.argv[2]
doc = json.loads(path.read_text(encoding="utf-8"))
arch_doc = doc.get(target_arch)
if not isinstance(arch_doc, dict):
    arch_doc = {}
items = arch_doc.get(
    "python-packages",
    doc.get("python-packages", doc.get("components", [])),
)
if not isinstance(items, list):
    raise SystemExit(
        f"source json must contain a \"python-packages\" list for target architecture {target_arch!r}, "
        "a top-level \"python-packages\" list, or a legacy \"components\" list"
    )
refs = []
for i, item in enumerate(items):
    if not isinstance(item, dict) or "vulcan" not in item:
        continue
    name = item.get("name")
    vulcan = item["vulcan"]
    if name != "sima_lmm[sdk]":
        raise SystemExit(
            f"component entry at index {i} uses unsupported Vulcan package {name!r}; "
            "only \"sima_lmm[sdk]\" is supported"
        )
    if not isinstance(vulcan, dict):
        raise SystemExit(f"component entry at index {i} requires vulcan to be an object")
    ref = vulcan.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise SystemExit(f"component entry at index {i} requires a non-empty vulcan.ref")
    refs.append(ref.strip())
if len(refs) > 1:
    raise SystemExit("source json contains multiple Vulcan-backed LLiMa packages")
if refs:
    print(refs[0])
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

python3 - \
  "$OUTPUT_DIR/resolved-llima-package.json" \
  "$REF" \
  "${wheels[0]}" <<'PY'
import json
import pathlib
import re
import sys
import zipfile
from email import message_from_bytes

output, requested_ref, wheel_raw = sys.argv[1:]
wheel = pathlib.Path(wheel_raw)
with zipfile.ZipFile(wheel) as archive:
    metadata_name = next(
        name for name in archive.namelist()
        if name.endswith(".dist-info/METADATA")
    )
    version = message_from_bytes(archive.read(metadata_name))["Version"]
if not version:
    raise SystemExit(f"Wheel version is missing from {wheel}")

explicit_commit = requested_ref.rpartition(":")[2] if ":" in requested_ref else ""
if re.fullmatch(r"[0-9a-fA-F]{7,40}", explicit_commit):
    resolved_commit = explicit_commit
else:
    match = re.search(r"(?:^|[.+-])([0-9a-fA-F]{7,40})$", version)
    if not match:
        raise SystemExit(
            f"Cannot determine the resolved commit from LLiMa wheel version {version!r}"
        )
    resolved_commit = match.group(1)

payload = {
    "sima_lmm": {
        "requested-ref": requested_ref,
        "resolved-commit": resolved_commit,
        "version": version,
        "wheel": wheel.name,
    }
}
pathlib.Path(output).write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)
PY

printf '%s\n' "${wheels[0]}"
