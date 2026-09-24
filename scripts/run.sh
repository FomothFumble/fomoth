#!/usr/bin/env bash
# Run the FOMOTH web server. Needs SOLANATRACKER_KEY in the environment.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${SOLANATRACKER_KEY:?set SOLANATRACKER_KEY (get one at https://www.solanatracker.io/data-api)}"
PORT="${1:-8090}"

exec python -m fomoth.server "$PORT"
