#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_SCRIPT="$REPO_ROOT/pre-validation-script.sh"

if [ ! -f "$ROOT_SCRIPT" ]; then
  printf "Error: missing canonical validator at %s\n" "$ROOT_SCRIPT" >&2
  exit 1
fi

exec "$ROOT_SCRIPT" "$@"