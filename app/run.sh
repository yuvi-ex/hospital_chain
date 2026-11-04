#!/usr/bin/env bash
# Hospital-chain demo, Streamlit fallback console: http://localhost:${HC_STREAMLIT_PORT:-8515}
set -euo pipefail
cd "$(dirname "$0")" || exit 1
PORT="${HC_STREAMLIT_PORT:-$(cat ../config.local.env ../config.env 2>/dev/null | grep -m1 '^HC_STREAMLIT_PORT=' | cut -d= -f2)}"
# the repository root on the path, so the pages can import hcconfig. Loopback only (--server.address): the page has no
# login and queries with the kit's admin profile, so it must never be reachable from the network.
PYTHONPATH="$(cd .. && pwd)${PYTHONPATH:+:$PYTHONPATH}" exec ../.venv/bin/streamlit run app.py --server.port "$PORT" --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
