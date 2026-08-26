#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUNDLE_DIR="${MODELSDK_BUNDLE_DIR:-}"
DOCKERFILE="${MODELSDK_CONTAINER_DOCKERFILE:-${REPO_ROOT}/container/Dockerfile}"
IMAGE="${MODELSDK_CONTAINER_IMAGE:-model-compiler:local}"
TARGET_ARCH="${MODELSDK_CONTAINER_ARCH:-amd64}"
SMOKE_TEST=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Build an Ubuntu 24.04 Model Compiler image from an existing local
bundle directory. This script does not build or download the bundle.

Options:
  --bundle-dir DIR   Bundle directory containing installer, manifest, and artifacts
                     (default: dist/<target-arch>/package)
  --image NAME:TAG   Local image reference (default: ${IMAGE})
  --target-arch ARCH Container architecture: amd64 or arm64 (default: ${TARGET_ARCH})
  --dockerfile FILE  Dockerfile path (default: ${DOCKERFILE})
  --smoke-test       Run the bundled basic smoke test after building
  -h, --help         Show this help

Environment overrides:
  MODELSDK_BUNDLE_DIR
  MODELSDK_CONTAINER_DOCKERFILE
  MODELSDK_CONTAINER_IMAGE
  MODELSDK_CONTAINER_ARCH
  MODELSDK_CONTAINER_GIT_BRANCH  Source branch override for detached checkouts
  MODELSDK_CONTAINER_GIT_HASH    Source commit override for detached checkouts
  MODELSDK_CONTAINER_GIT_TAG     Exact source tag override
  MODELSDK_CONTAINER_SOURCE_URL  OCI source URL label
  MODELSDK_CONTAINER_BUILD_TIME  UTC ISO-8601 timestamp (defaults to current time)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle-dir)
      BUNDLE_DIR="${2:-}"
      shift 2
      ;;
    --image)
      IMAGE="${2:-}"
      shift 2
      ;;
    --target-arch)
      TARGET_ARCH="${2:-}"
      shift 2
      ;;
    --dockerfile)
      DOCKERFILE="${2:-}"
      shift 2
      ;;
    --smoke-test)
      SMOKE_TEST=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "${TARGET_ARCH}" in
  amd64|x86_64)
    TARGET_ARCH="amd64"
    DOCKER_PLATFORM="linux/amd64"
    MODELSDK_TARGET_ARCH="x86_64"
    ;;
  arm64|aarch64)
    TARGET_ARCH="arm64"
    DOCKER_PLATFORM="linux/arm64"
    MODELSDK_TARGET_ARCH="aarch64"
    ;;
  *)
    echo "Unsupported target architecture: ${TARGET_ARCH}" >&2
    echo "Use --target-arch amd64 or --target-arch arm64." >&2
    exit 2
    ;;
esac

BUNDLE_DIR="${BUNDLE_DIR:-${REPO_ROOT}/dist/${TARGET_ARCH}/package}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to build the Model Compiler container." >&2
  exit 1
fi
if [[ ! -d "${BUNDLE_DIR}" ]]; then
  echo "Model Compiler bundle directory not found: ${BUNDLE_DIR}" >&2
  echo "Build the ${TARGET_ARCH} bundle first, then pass its package directory with --bundle-dir." >&2
  exit 1
fi
if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Dockerfile not found: ${DOCKERFILE}" >&2
  exit 1
fi
for required in install_modelsdk_wheels.sh source.json manifest.txt; do
  if [[ ! -f "${BUNDLE_DIR}/${required}" ]]; then
    echo "Bundle directory is missing ${required}: ${BUNDLE_DIR}" >&2
    exit 1
  fi
done
for sensitive in .netrc .git-credentials id_rsa id_ed25519; do
  if [[ -e "${BUNDLE_DIR}/${sensitive}" ]]; then
    echo "Refusing bundle directory containing credential file ${sensitive}: ${BUNDLE_DIR}" >&2
    exit 1
  fi
done
if ! find "${BUNDLE_DIR}" -maxdepth 1 -type f -name '*.whl' -print -quit | grep -q .; then
  echo "Bundle directory contains no wheel files: ${BUNDLE_DIR}" >&2
  exit 1
fi
if ! docker buildx version >/dev/null 2>&1; then
  echo "Docker Buildx is required for the local bundle build context." >&2
  exit 1
fi

BUNDLE_DIR="$(cd "${BUNDLE_DIR}" && pwd)"
DOCKERFILE="$(cd "$(dirname "${DOCKERFILE}")" && pwd)/$(basename "${DOCKERFILE}")"

git_branch="${MODELSDK_CONTAINER_GIT_BRANCH:-}"
git_hash="${MODELSDK_CONTAINER_GIT_HASH:-}"
git_tag="${MODELSDK_CONTAINER_GIT_TAG:-}"

if [[ -z "${git_branch}" ]]; then
  git_branch="$(git -C "${REPO_ROOT}" branch --show-current 2>/dev/null || true)"
fi
if [[ -z "${git_hash}" ]]; then
  git_hash="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || true)"
else
  git_hash="${git_hash:0:7}"
fi

if [[ -z "${git_tag}" && "${GITHUB_REF_TYPE:-}" == "tag" ]]; then
  git_tag="${GITHUB_REF_NAME:-}"
elif [[ -z "${git_tag}" && -z "${GITHUB_REF_TYPE:-}" ]]; then
  git_tag="$(git -C "${REPO_ROOT}" describe --tags --exact-match HEAD 2>/dev/null || true)"
fi

if [[ -z "${git_branch}" ]]; then
  if [[ "${GITHUB_REF_TYPE:-}" == "branch" ]]; then
    git_branch="${GITHUB_REF_NAME:-}"
  else
    git_branch="${GITHUB_HEAD_REF:-unknown}"
  fi
fi
git_hash="${git_hash:-nogit}"

# Only stable release tags replace the branch:hash development version.
if [[ "${git_tag}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
  model_compiler_version="${git_tag}"
else
  model_compiler_version="${git_branch}:${git_hash}"
fi
build_time="${MODELSDK_CONTAINER_BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
source_url="${MODELSDK_CONTAINER_SOURCE_URL:-}"

echo "Building ${IMAGE}"
echo "Platform: ${DOCKER_PLATFORM}"
echo "Model Compiler version: ${model_compiler_version}"
echo "Build time: ${build_time}"
echo "Bundle directory: ${BUNDLE_DIR}"
echo "Dockerfile: ${DOCKERFILE}"

docker buildx build \
  --load \
  --platform "${DOCKER_PLATFORM}" \
  --build-context "modelsdk_bundle=${BUNDLE_DIR}" \
  --build-arg "MODEL_COMPILER_TARGET_ARCH=${MODELSDK_TARGET_ARCH}" \
  --build-arg "MODEL_COMPILER_SMOKE_ARCH=${TARGET_ARCH}" \
  --build-arg "MODEL_COMPILER_GIT_BRANCH=${git_branch}" \
  --build-arg "MODEL_COMPILER_GIT_HASH=${git_hash}" \
  --build-arg "MODEL_COMPILER_VERSION=${model_compiler_version}" \
  --build-arg "MODEL_COMPILER_BUILD_TIME=${build_time}" \
  --build-arg "MODEL_COMPILER_SOURCE_URL=${source_url}" \
  --file "${DOCKERFILE}" \
  --tag "${IMAGE}" \
  "${REPO_ROOT}"

if [[ "${SMOKE_TEST}" == "1" ]]; then
  docker run --rm "${IMAGE}" \
    python /opt/model-compiler-tests/scripts/smoke_test_modelsdk.py --tier basic
fi

cat <<EOF

Built ${IMAGE}

Interactive login shell:
  docker run --rm -it -v "\${PWD}:/workspace" ${IMAGE}

Basic smoke test:
  docker run --rm ${IMAGE} python /opt/model-compiler-tests/scripts/smoke_test_modelsdk.py --tier basic

Compile smoke test with persistent artifacts:
  mkdir -p modelsdk-smoke
  docker run --rm -v "\${PWD}/modelsdk-smoke:/workspace/modelsdk-smoke" ${IMAGE} \\
    python /opt/model-compiler-tests/scripts/smoke_test_modelsdk.py \\
      --tier resnet-compile --work-dir /workspace/modelsdk-smoke
EOF
