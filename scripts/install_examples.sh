#!/usr/bin/env bash
set -euo pipefail

install_root="$(pwd)"
archive="${install_root}/model-compiler-examples.zip"

if [[ ! -f "${archive}" ]]; then
  echo "Missing examples archive: ${archive}" >&2
  echo "Build the package first with: scripts/build_examples.sh" >&2
  exit 1
fi

model_compiler_locations=(
  "${VIRTUAL_ENV:-}"
  "/sdk-extensions/model-compiler"
  "/sdk-add-on/model-compiler"
  "${HOME}/sdk-extensions/model-compiler"
)

model_compiler_installed="false"
for location in "${model_compiler_locations[@]}"; do
  if [[ -n "${location}" && -f "${location}/bin/activate" ]]; then
    model_compiler_installed="true"
    break
  fi
done

if ! command -v activate-model-compiler >/dev/null 2>&1 && [[ "${model_compiler_installed}" != "true" ]]; then
  cat >&2 <<'EOF'
Model Compiler is not installed in this environment.

Install Model Compiler first, then retry:
  sima-cli install tools/model-compiler/arm64

Use the package/version appropriate for your SDK environment.
EOF
  exit 1
fi

active_virtual_env="${VIRTUAL_ENV:-}"
active_virtual_env="${active_virtual_env%/}"

if [[ -z "${active_virtual_env}" || "${active_virtual_env}" != *model-compiler ]]; then
  cat >&2 <<'EOF'
Model Compiler is installed but its virtual environment is not active.

Activate it first, then retry:
  activate-model-compiler

If that command is not available, reload your shell profile or reinstall Model
Compiler so the activation helper is added to your shell.
EOF
  exit 1
fi

if [[ ! -x "${active_virtual_env}/bin/python" ]]; then
  cat >&2 <<EOF
The active Model Compiler virtual environment is missing its Python executable.

Active virtual environment:
  ${active_virtual_env}

Reactivate or reinstall Model Compiler, then retry:
  activate-model-compiler
EOF
  exit 1
fi

shopt -s nullglob
afe_packages=("${active_virtual_env}"/lib/python*/site-packages/afe)
shopt -u nullglob
if [[ "${#afe_packages[@]}" -eq 0 ]]; then
  cat >&2 <<EOF
The active virtual environment does not appear to contain Model Compiler's
'afe' package.

Active virtual environment:
  ${active_virtual_env}

Reactivate Model Compiler, then retry:
  activate-model-compiler
EOF
  exit 1
fi

python3 -m zipfile -e "${archive}" "${install_root}"

find "${install_root}" -type f -name '*.py' -exec chmod a+x {} +

cat <<EOF
Model Compiler examples installed in:
  ${install_root}

Run an example from this directory, for example:
  python3 compile_first_model.py
EOF
