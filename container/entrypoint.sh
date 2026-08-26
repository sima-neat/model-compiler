#!/usr/bin/env bash
set -e

# shellcheck source=container/model-compiler-shell.sh
. /etc/profile.d/model-compiler.sh

exec "$@"
