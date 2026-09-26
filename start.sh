#!/usr/bin/env bash
# Start Ticket Resolver.
#
#     ./start.sh
#
# Starts TrueForge if it isn't already up, provisions the agent, and runs the
# health check. Safe to re-run - nothing here is destructive.

set -euo pipefail
cd "$(dirname "$0")"

BASE_URL="http://localhost:8790"

trueforge_up() {
    curl -sf -o /dev/null --max-time 3 "$BASE_URL/api/v1/capabilities"
}

# 1. Node version -----------------------------------------------------------
node_version=$(node -v | sed 's/^v//')
major=${node_version%%.*}
rest=${node_version#*.}
minor=${rest%%.*}
if [ "$major" -lt 22 ] || { [ "$major" -eq 22 ] && [ "$minor" -lt 14 ]; }; then
    echo "Node $node_version is too old - TrueForge needs >= 22.14" >&2
    exit 1
fi
echo "node v$node_version"

# 2. TrueForge --------------------------------------------------------------
if trueforge_up; then
    echo "TrueForge already running at $BASE_URL"
else
    echo "starting TrueForge..."
    nohup npx -y @truefoundry/trueforge > trueforge.log 2>&1 &

    for _ in $(seq 1 60); do
        if trueforge_up; then break; fi
        sleep 2
    done

    if ! trueforge_up; then
        echo "TrueForge did not come up within 120s. See trueforge.log" >&2
        exit 1
    fi
    echo "TrueForge up at $BASE_URL"
fi

# 3. Provision + verify -----------------------------------------------------
python setup.py

if python verify.py; then
    echo
    echo "Ready. Open $BASE_URL and start a session with 'ticket-resolver'."
    echo "Or from the terminal:"
    echo "    python run_ticket.py SAN-5     reproduce -> patch -> approval"
    echo "    python run_ticket.py SAN-6     honest 'could not reproduce'"
else
    echo
    echo "Some checks failed - see above." >&2
    exit 1
fi
