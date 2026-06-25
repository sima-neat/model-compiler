#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/build_examples.sh [--output-dir dist/examples]

Builds the Model Compiler examples package:
  - stages examples/ into a temporary build directory
  - removes generated calibration pickle files
  - creates model-compiler-examples.zip
  - copies install_examples.sh
  - runs sima-cli packages build to generate metadata.json
EOF
}

OUTPUT_DIR="dist/examples"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR_ABS="$(cd "${REPO_ROOT}" && mkdir -p "$(dirname "${OUTPUT_DIR}")" && python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "${OUTPUT_DIR}")"
ZIP_NAME="model-compiler-examples.zip"

if ! command -v sima-cli >/dev/null 2>&1; then
  echo "sima-cli is required on PATH." >&2
  exit 1
fi

BUILD_ROOT="$(mktemp -d)"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

STAGED_EXAMPLES="${BUILD_ROOT}/model-compiler-examples"
rm -rf "${OUTPUT_DIR_ABS}"
mkdir -p "${STAGED_EXAMPLES}" "${OUTPUT_DIR_ABS}"

cp -R "${REPO_ROOT}/examples/." "${STAGED_EXAMPLES}/"
find "${STAGED_EXAMPLES}" -type f -name '*.pkl' -delete

python3 - "${STAGED_EXAMPLES}" "${OUTPUT_DIR_ABS}/${ZIP_NAME}" <<'PY'
import sys
import zipfile
from pathlib import Path

source = Path(sys.argv[1])
output = Path(sys.argv[2])
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(source).as_posix())
PY

cp "${SCRIPT_DIR}/install_examples.sh" "${OUTPUT_DIR_ABS}/"

sima-cli packages build "${OUTPUT_DIR_ABS}" \
  --name gh:sima-neat/model-compiler/examples \
  --description "SiMa.ai Model Compiler example scripts." \
  --install-script install_examples.sh \
  --host-platform ubuntu@==22.04 \
  --host-platform ubuntu@==24.04 \
  --palette-platform

python3 -m json.tool "${OUTPUT_DIR_ABS}/metadata.json" >/dev/null
if python3 -m zipfile -l "${OUTPUT_DIR_ABS}/${ZIP_NAME}" | grep -F 'compile_first_model.py' | grep -Fv 'resnet50-ptq/compile_first_model.py' >/dev/null; then
  echo "Unexpected root compile_first_model.py in examples package." >&2
  exit 1
fi
python3 -m zipfile -l "${OUTPUT_DIR_ABS}/${ZIP_NAME}" | grep -F 'resnet50-ptq/compile_first_model.py' >/dev/null
python3 -m zipfile -l "${OUTPUT_DIR_ABS}/${ZIP_NAME}" | grep -F 'resnet50-ptq/src/modelsdk_quantize_model/resnet50_quant.py' >/dev/null

echo "Examples package written to: ${OUTPUT_DIR_ABS}"
