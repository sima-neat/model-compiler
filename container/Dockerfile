# syntax=docker/dockerfile:1.7

ARG MODEL_COMPILER_BASE_IMAGE=ubuntu:24.04
FROM ${MODEL_COMPILER_BASE_IMAGE}

ARG PYENV_VERSION=v2.8.4
ARG MODEL_COMPILER_TARGET_ARCH=x86_64
ARG MODEL_COMPILER_SMOKE_ARCH=amd64

ENV DEBIAN_FRONTEND=noninteractive \
    PYENV_ROOT=/opt/pyenv \
    MODEL_COMPILER_HOME=/sdk-extensions/model-compiler \
    MODEL_COMPILER_SMOKE_ROOT=/opt/model-compiler-tests \
    MODELSDK_SMOKE_ARCH="${MODEL_COMPILER_SMOKE_ARCH}" \
    VIRTUAL_ENV=/sdk-extensions/model-compiler

# The bundle installer needs Python to read source.json before it installs the
# manifest's Ubuntu dependencies. git and ca-certificates install pinned pyenv.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        ca-certificates \
        git \
        python3 \
        python3-venv \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --branch "${PYENV_VERSION}" --depth 1 \
        https://github.com/pyenv/pyenv.git "${PYENV_ROOT}" \
    && rm -rf "${PYENV_ROOT}/.git"

# modelsdk_bundle is supplied by scripts/build_modelsdk_container.sh as a local
# directory. A BuildKit bind mount keeps the large wheel set and any package
# credentials out of image layers. The rw mount is intentional: the existing
# installer removes consumed bundle artifacts, and BuildKit discards those
# mount changes after this step.
RUN --mount=type=bind,from=modelsdk_bundle,source=.,target=/tmp/modelsdk-bundle,rw \
    test -f /tmp/modelsdk-bundle/install_modelsdk_wheels.sh \
    && test -f /tmp/modelsdk-bundle/source.json \
    && test -f /tmp/modelsdk-bundle/manifest.txt \
    && mkdir -p /sdk-extensions \
    && MODELSDK_TARGET_ARCH="${MODEL_COMPILER_TARGET_ARCH}" \
        bash /tmp/modelsdk-bundle/install_modelsdk_wheels.sh \
    && test -x "${MODEL_COMPILER_HOME}/bin/python"

# Minimal Ubuntu does not include GLib, while the compiler's EV transforms use
# libgthread at runtime. This dependency is normally already present on a full
# Ubuntu workstation but must be explicit in the container.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Keep volatile build metadata below the bundle installation layers so a new
# timestamp does not force the multi-gigabyte package installation to rerun.
ARG MODEL_COMPILER_GIT_BRANCH=unknown
ARG MODEL_COMPILER_GIT_HASH=nogit
ARG MODEL_COMPILER_VERSION=unknown:nogit
ARG MODEL_COMPILER_BUILD_TIME=unknown
ARG MODEL_COMPILER_SOURCE_URL=""

ENV MODEL_COMPILER_GIT_BRANCH="${MODEL_COMPILER_GIT_BRANCH}" \
    MODEL_COMPILER_GIT_HASH="${MODEL_COMPILER_GIT_HASH}" \
    MODEL_COMPILER_VERSION="${MODEL_COMPILER_VERSION}" \
    MODEL_COMPILER_BUILD_TIME="${MODEL_COMPILER_BUILD_TIME}"

LABEL org.opencontainers.image.source="${MODEL_COMPILER_SOURCE_URL}"

RUN printf '%s\n' \
      "Model Compiler Version = ${MODEL_COMPILER_VERSION}" \
      "Git Branch = ${MODEL_COMPILER_GIT_BRANCH}" \
      "Git Commit = ${MODEL_COMPILER_GIT_HASH}" \
      "Build Time (UTC) = ${MODEL_COMPILER_BUILD_TIME}" \
      > /etc/sdk-release

COPY container/model-compiler-shell.sh /etc/profile.d/model-compiler.sh
COPY container/entrypoint.sh /usr/local/bin/model-compiler-entrypoint
COPY scripts/smoke_test_modelsdk.py ${MODEL_COMPILER_SMOKE_ROOT}/scripts/smoke_test_modelsdk.py
COPY skills/model_surgery ${MODEL_COMPILER_SMOKE_ROOT}/skills/model_surgery
COPY skills/quantize_compile ${MODEL_COMPILER_SMOKE_ROOT}/skills/quantize_compile

RUN chmod 0755 \
        /etc/profile.d/model-compiler.sh \
        /usr/local/bin/model-compiler-entrypoint \
        "${MODEL_COMPILER_SMOKE_ROOT}/scripts/smoke_test_modelsdk.py" \
    && printf '\n# Model Compiler container environment\n. /etc/profile.d/model-compiler.sh\n' \
        >> /root/.bashrc \
    && mkdir -p /workspace

ENV PATH="/sdk-extensions/model-compiler/bin:/opt/pyenv/shims:/opt/pyenv/bin:${PATH}" \
    LD_LIBRARY_PATH="/sdk-extensions/model-compiler/lib:/sdk-extensions/model-compiler/lib/python3.12/site-packages:/sdk-extensions/model-compiler/lib/python3.12/site-packages/tvm" \
    PYTHONPATH="/sdk-extensions/model-compiler/lib/python3.12/site-packages"

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/model-compiler-entrypoint"]
CMD ["bash", "-l"]
