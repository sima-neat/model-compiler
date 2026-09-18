#!/usr/bin/env bash

# This file is sourced by the container entrypoint and by login/interactive
# shells. Keep it idempotent because a login Bash can encounter it twice via
# /etc/profile and /root/.bashrc.
if [ "${_MODEL_COMPILER_CONTAINER_SHELL_INITIALIZED:-0}" != "1" ]; then
  _MODEL_COMPILER_CONTAINER_SHELL_INITIALIZED=1

  export PYENV_ROOT="${PYENV_ROOT:-/opt/pyenv}"
  case ":${PATH}:" in
    *":${PYENV_ROOT}/bin:"*) ;;
    *) PATH="${PYENV_ROOT}/bin:${PATH}" ;;
  esac
  export PATH

  if command -v pyenv >/dev/null 2>&1; then
    eval "$(pyenv init - bash)"
  fi

  model_compiler_home="${MODEL_COMPILER_HOME:-/sdk-extensions/model-compiler}"
  if [ -f "${model_compiler_home}/bin/activate" ] \
    && { [ "${VIRTUAL_ENV:-}" != "${model_compiler_home}" ] \
      || ! command -v deactivate >/dev/null 2>&1; }; then
    # The container prompt below carries the environment name and version.
    export VIRTUAL_ENV_DISABLE_PROMPT=1
    # shellcheck disable=SC1090
    . "${model_compiler_home}/bin/activate"
  fi

  unset model_compiler_home
fi

# Ubuntu's login sequence can source this file before and after .bashrc resets
# PS1. Apply the idempotent prompt decoration on every interactive sourcing.
case "$-" in
  *i*)
    model_compiler_prompt="[model-compiler ${MODEL_COMPILER_VERSION:-unknown:nogit}]"
    case "${PS1:-}" in
      "${model_compiler_prompt}"*) ;;
      *) PS1="${model_compiler_prompt} ${PS1:-\\u@\\h:\\w\\\$ }" ;;
    esac
    export PS1
    unset model_compiler_prompt
    ;;
esac
