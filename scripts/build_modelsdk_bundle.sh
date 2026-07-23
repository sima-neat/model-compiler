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
    [--target-arch x86_64|aarch64] \
    [--prod]

Description:
  End-to-end helper:
    1) Read python/binary package lists from source.json
    2) Clean generated artifacts from output-dir
    3) Download the full wheel dependency closure and binary artifacts
    4) Copy installer script into output-dir
    5) Create a self-contained archive and metadata.json for sima-cli distribution
    6) Optional --prod escapes '+' as '%2B' in metadata resources for S3 URLs

source.json format:
{
  "sdk_version": "2.0.0",
  "python_version": "3.10",
  "python-packages": [
    { "name": "sima-frontend", "version": "2.0.0.dev0+master.371" }
  ],
  "binary-packages": [
    {
      "name": "mla/toolchain/mla-toolchain",
      "version": "v2.1.3560-develop.409",
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
BUNDLE_VERSION_EXPLICIT="0"
OUTPUT_DIR="./dist"
NAME="sima-neat-model-compiler"
RELEASE="stable"
DESCRIPTION="SiMa.ai NEAT Model Compiler"
BOARD_COMPATIBLE="modalix"
BOARD_VERSION=""
PYTHON_VERSION=""
HOST_OS="linux"
TARGET_ARCH="${MODELSDK_TARGET_ARCH:-}"
PROD_MODE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-json) SOURCE_JSON="${2:-}"; shift 2 ;;
    --index-url) INDEX_URL="${2:-}"; shift 2 ;;
    --extra-index-url) EXTRA_INDEX_URL="${2:-}"; shift 2 ;;
    --bundle-version) BUNDLE_VERSION="${2:-}"; BUNDLE_VERSION_EXPLICIT="1"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --name) NAME="${2:-}"; shift 2 ;;
    --release) RELEASE="${2:-}"; shift 2 ;;
    --description) DESCRIPTION="${2:-}"; shift 2 ;;
    --host-os) HOST_OS="${2:-}"; shift 2 ;;
    --python-version) PYTHON_VERSION="${2:-}"; shift 2 ;;
    --target-arch) TARGET_ARCH="${2:-}"; shift 2 ;;
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

normalize_target_arch() {
  local raw="$1"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    "" )
      case "$(uname -m 2>/dev/null || echo unknown)" in
        x86_64|amd64) echo "x86_64" ;;
        aarch64|arm64) echo "aarch64" ;;
        *) echo "" ;;
      esac
      ;;
    x86_64|amd64) echo "x86_64" ;;
    aarch64|arm64) echo "aarch64" ;;
    *) echo "" ;;
  esac
}

TARGET_ARCH="$(normalize_target_arch "$TARGET_ARCH")"
if [[ -z "$TARGET_ARCH" ]]; then
  echo "Unable to resolve target architecture. Use --target-arch x86_64 or --target-arch aarch64." >&2
  exit 1
fi
echo "Using target architecture: $TARGET_ARCH"
case "$TARGET_ARCH" in
  x86_64) PACKAGE_ARCH="amd64" ;;
  aarch64) PACKAGE_ARCH="arm64" ;;
  *) PACKAGE_ARCH="$TARGET_ARCH" ;;
esac

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

SCRIPT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$BUNDLE_VERSION_EXPLICIT" == "0" ]]; then
  GIT_TAG="$(
    git -C "$SCRIPT_HOME/.." tag --points-at HEAD 2>/dev/null \
      | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
      | sort -V \
      | tail -n1 || true
  )"
  if [[ -n "$GIT_TAG" ]]; then
    BUNDLE_VERSION="${GIT_TAG#v}"
    echo "Using git tag version for metadata: $BUNDLE_VERSION"
  fi
fi

if [[ "$BUNDLE_VERSION" == *"sdk_version"* ]]; then
  if [[ -z "$SDK_VERSION" ]]; then
    echo "sdk_version is missing in $SOURCE_JSON but bundle version requires it." >&2
    exit 1
  fi
  BUNDLE_VERSION="${BUNDLE_VERSION//sdk_version/$SDK_VERSION}"
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
  # Accept 3.10 / 3.11 / 3.12, patch versions like 3.12.3, or 310 / 311 / 312;
  # normalize to the ABI tag form expected by pip wheel selection.
  PYTHON_VERSION="$(echo "$PYTHON_VERSION" | sed -E 's/^([0-9]+)\.([0-9]+)(\.[0-9]+)?$/\1\2/')"
fi
if [[ -z "$PYTHON_VERSION" ]]; then
  PYTHON_VERSION="312"
fi

build_tmp_dir="$(mktemp -d)"
trap 'rm -rf "$build_tmp_dir"' EXIT
spec_file="${build_tmp_dir}/sdk-release.txt"
python3 -c '
import json, sys
path = sys.argv[1]
target_arch = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    doc = json.load(f)
arch_doc = doc.get(target_arch)
if not isinstance(arch_doc, dict):
    arch_doc = {}
items = arch_doc.get("python-packages", doc.get("python-packages", doc.get("components", doc)))
if not isinstance(items, list):
    raise SystemExit(
        f"source json must contain a \"python-packages\" list for target architecture {target_arch!r}, "
        "a top-level \"python-packages\" list, or a legacy \"components\" list"
    )
for i, item in enumerate(items):
    if not isinstance(item, dict):
        raise SystemExit(f"component entry at index {i} is not an object")
    name = item.get("name")
    version = item.get("version")
    url = item.get("url")
    file = item.get("file")
    if not name:
        raise SystemExit(f"component entry at index {i} requires name")
    if "vulcan" in item:
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
        continue
    if not version:
        raise SystemExit(f"component entry at index {i} requires name and version")
    if isinstance(url, str) and url.strip():
        print(f"{name} @ {url.strip()}")
    elif isinstance(file, str) and file.strip():
        print(f"{name} @ {file.strip()}")
    else:
        print(f"{name}=={version}")
' "$SOURCE_JSON" "$TARGET_ARCH" > "$spec_file"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUTPUT_DIR"

echo "Cleaning generated bundle artifacts from: $OUTPUT_DIR"
find "$OUTPUT_DIR" -maxdepth 1 -type f \( \
  -name '*.whl' \
  -o -name '*.tar.gz' \
  -o -name '*.zip' \
  -o -name 'manifest.txt' \
  -o -name 'metadata*.json' \
  -o -name 'resolved-llima-package.json' \
  -o -name 'source.json' \
  -o -name 'install_modelsdk_wheels.sh' \
\) -delete

download_args=(
  --sdk-release "$spec_file" \
  --index-url "$INDEX_URL" \
  --extra-index-url "$EXTRA_INDEX_URL" \
  --output-dir "$OUTPUT_DIR" \
  --source-json "$SOURCE_JSON" \
  --python-version "$PYTHON_VERSION" \
  --target-arch "$TARGET_ARCH"
)
download_args+=(--include-dependencies)
"$SCRIPT_DIR/download_modelsdk_wheels.sh" "${download_args[@]}"

cp "$SCRIPT_DIR/install_modelsdk_wheels.sh" "$OUTPUT_DIR/"
cp "$SOURCE_JSON" "$OUTPUT_DIR/source.json"

metadata_args=(
  --artifacts-dir "$OUTPUT_DIR" \
  --output "$OUTPUT_DIR/metadata.json" \
  --name "$NAME" \
  --version "$BUNDLE_VERSION" \
  --release "$RELEASE" \
  --description "$DESCRIPTION" \
  --host-os "$HOST_OS" \
  --target-arch "$TARGET_ARCH" \
  --installer-script "install_modelsdk_wheels.sh" \
  --archive-name "model-compiler-${PACKAGE_ARCH}.zip"
)
resolved_packages="$OUTPUT_DIR/resolved-llima-package.json"
if [[ -f "$resolved_packages" ]]; then
  metadata_args+=(--resolved-packages "$resolved_packages")
fi
"$SCRIPT_DIR/generate_metadata.py" "${metadata_args[@]}"
rm -f "$resolved_packages"

if [[ "$PROD_MODE" == "1" ]]; then
  python3 -c '
import json, sys

def esc(s):
    return s.replace("+", "%2B")

for raw_path in sys.argv[1:]:
    path = raw_path
    with open(path, "r", encoding="utf-8") as f:
        m = json.load(f)

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
        f.write("\n")
' "$OUTPUT_DIR/metadata.json" "$OUTPUT_DIR/metadata-offline.json"
  echo "Applied --prod metadata escaping ('+' -> '%2B')"
fi

echo "Bundle generated in: $OUTPUT_DIR"
