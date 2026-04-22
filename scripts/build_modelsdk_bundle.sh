#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  build_modelsdk_bundle.sh \
    [--index-url https://artifacts.eng.sima.ai/artifactory/api/pypi/sima-pypi-group/simple] \
    [--extra-index-url https://pypi.org/simple] \
    [--bundle-version sdk_version.neat+branch.git-short-hash] \
    [--output-dir ./dist] \
    [--source-json ./scripts/source.json] \
    [--prod]

Description:
  End-to-end helper:
    1) Read python/binary package lists from source.json
    2) Download wheels (pure first, x86 fallback) and binary artifacts
    3) Copy installer script into output-dir
    4) Generate metadata.json for sima-cli distribution
    5) Optional --prod escapes '+' as '%2B' in metadata resources for S3 URLs

source.json format:
{
  "sdk_version": "2.0.0",
  "python_version": "3.10",
  "python-packages": [
    { "name": "sima-frontend", "version": "2.0.0.dev0+master.371" }
  ],
  "binary-packages": [
    {
      "name": "toolchain/mla/mla-toolchain",
      "version": "v2.1.3158-Edgematic-release-2.0.0.2-ubuntu",
      "extension": ".zip"
    }
  ]
}
EOF
}

SOURCE_JSON=""
INDEX_URL="https://artifacts.eng.sima.ai/artifactory/api/pypi/sima-pypi-group/simple"
EXTRA_INDEX_URL="https://pypi.org/simple"
BUNDLE_VERSION="sdk_version.neat+branch.git-short-hash"
OUTPUT_DIR="./dist"
NAME="sima-neat-model-sdk"
RELEASE="stable"
DESCRIPTION="SiMa.ai NEAT Model SDK"
BOARD_COMPATIBLE="modalix"
BOARD_VERSION=""
PYTHON_VERSION=""
HOST_OS="linux"
PROD_MODE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-json) SOURCE_JSON="${2:-}"; shift 2 ;;
    --index-url) INDEX_URL="${2:-}"; shift 2 ;;
    --extra-index-url) EXTRA_INDEX_URL="${2:-}"; shift 2 ;;
    --bundle-version) BUNDLE_VERSION="${2:-}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --name) NAME="${2:-}"; shift 2 ;;
    --release) RELEASE="${2:-}"; shift 2 ;;
    --description) DESCRIPTION="${2:-}"; shift 2 ;;
    --host-os) HOST_OS="${2:-}"; shift 2 ;;
    --python-version) PYTHON_VERSION="${2:-}"; shift 2 ;;
    --prod) PROD_MODE="1"; shift 1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$SOURCE_JSON" ]]; then
  SOURCE_JSON="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/source.json"
fi
if [[ ! -f "$SOURCE_JSON" ]]; then
  echo "source json file not found: $SOURCE_JSON" >&2
  exit 1
fi
echo "Using package manifest: $SOURCE_JSON"

SDK_VERSION="$(
  python3 -c '
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    doc = json.load(f)
v = doc.get("sdk_version", "")
if isinstance(v, str):
    print(v.strip())
' "$SOURCE_JSON"
)"

if [[ "$BUNDLE_VERSION" == *"sdk_version"* ]]; then
  if [[ -z "$SDK_VERSION" ]]; then
    echo "sdk_version is missing in $SOURCE_JSON but bundle version requires it." >&2
    exit 1
  fi
  BUNDLE_VERSION="${BUNDLE_VERSION//sdk_version/$SDK_VERSION}"
fi

if [[ "$BUNDLE_VERSION" == *"branch.git"* || "$BUNDLE_VERSION" == *"short-hash"* ]]; then
  SCRIPT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [[ "$BUNDLE_VERSION" == *"branch.git"* ]]; then
  GIT_BRANCH="$(git -C "$SCRIPT_HOME/.." rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ -z "$GIT_BRANCH" || "$GIT_BRANCH" == "HEAD" ]]; then
    GIT_BRANCH="unknown-branch"
    echo "Warning: unable to resolve git branch; using '$GIT_BRANCH'." >&2
  fi
  # Make branch token safe for version strings.
  GIT_BRANCH_SAFE="$(echo "$GIT_BRANCH" | sed -E 's/[^A-Za-z0-9._-]+/-/g')"
  BUNDLE_VERSION="${BUNDLE_VERSION//branch.git/$GIT_BRANCH_SAFE}"
fi

if [[ "$BUNDLE_VERSION" == *"short-hash"* ]]; then
  GIT_SHORT_HASH="$(git -C "$SCRIPT_HOME/.." rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "$GIT_SHORT_HASH" ]]; then
    GIT_SHORT_HASH="unknown"
    echo "Warning: unable to resolve git short hash; using '$GIT_SHORT_HASH'." >&2
  fi
  BUNDLE_VERSION="${BUNDLE_VERSION//short-hash/$GIT_SHORT_HASH}"
fi

if [[ -z "$PYTHON_VERSION" ]]; then
  PYTHON_VERSION="$(
    python3 -c '
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    doc = json.load(f)
v = doc.get("python_version", "")
if isinstance(v, str):
    print(v.strip())
' "$SOURCE_JSON"
  )"
fi
if [[ -n "$PYTHON_VERSION" ]]; then
  # Accept 3.10 / 3.11 / 3.12 or 310 / 311 / 312; normalize to 310/311/312.
  PYTHON_VERSION="$(echo "$PYTHON_VERSION" | sed -E 's/^([0-9]+)\.([0-9]+)$/\1\2/')"
fi
if [[ -z "$PYTHON_VERSION" ]]; then
  PYTHON_VERSION="312"
fi

spec_file="$(mktemp)"
trap 'rm -f "$spec_file"' EXIT
python3 -c '
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    doc = json.load(f)
items = doc.get("python-packages", doc.get("components", doc))
if not isinstance(items, list):
    raise SystemExit("source json must contain a \"python-packages\" list (or legacy \"components\" list)")
for i, item in enumerate(items):
    if not isinstance(item, dict):
        raise SystemExit(f"component entry at index {i} is not an object")
    name = item.get("name")
    version = item.get("version")
    if not name or not version:
        raise SystemExit(f"component entry at index {i} requires name and version")
    print(f"{name}=={version}")
' "$SOURCE_JSON" > "$spec_file"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUTPUT_DIR"

"$SCRIPT_DIR/download_modelsdk_wheels.sh" \
  --sdk-release "$spec_file" \
  --index-url "$INDEX_URL" \
  --extra-index-url "$EXTRA_INDEX_URL" \
  --output-dir "$OUTPUT_DIR" \
  --source-json "$SOURCE_JSON" \
  --python-version "$PYTHON_VERSION"

cp "$SCRIPT_DIR/install_modelsdk_wheels.sh" "$OUTPUT_DIR/"
cp "$SOURCE_JSON" "$OUTPUT_DIR/source.json"

"$SCRIPT_DIR/generate_metadata.py" \
  --artifacts-dir "$OUTPUT_DIR" \
  --output "$OUTPUT_DIR/metadata.json" \
  --name "$NAME" \
  --version "$BUNDLE_VERSION" \
  --release "$RELEASE" \
  --description "$DESCRIPTION" \
  --host-os "$HOST_OS" \
  --installer-script "install_modelsdk_wheels.sh"

if [[ "$PROD_MODE" == "1" ]]; then
  python3 -c '
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    m = json.load(f)

def esc(s):
    return s.replace("+", "%2B")

resources = m.get("resources", [])
m["resources"] = [esc(r) if isinstance(r, str) else r for r in resources]

rc = m.get("resources-checksum", {})
if isinstance(rc, dict):
    m["resources-checksum"] = {
        (esc(k) if isinstance(k, str) else k): v for k, v in rc.items()
    }

sel = m.get("selectable-resources", [])
if isinstance(sel, list):
    for entry in sel:
        if isinstance(entry, dict):
            if isinstance(entry.get("url"), str):
                entry["url"] = esc(entry["url"])
            if isinstance(entry.get("resource"), str):
                entry["resource"] = esc(entry["resource"])

with open(path, "w", encoding="utf-8") as f:
    json.dump(m, f, indent=2)
    f.write("\\n")
' "$OUTPUT_DIR/metadata.json"
  echo "Applied --prod metadata escaping ('+' -> '%2B')"
fi

echo "Bundle generated in: $OUTPUT_DIR"
