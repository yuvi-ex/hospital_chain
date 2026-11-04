#!/usr/bin/env bash
# Create the project's Python environment (.venv) with uv. Idempotent.
source "$(dirname "$0")/common.sh"
command -v uv >/dev/null || die "uv is not installed: https://docs.astral.sh/uv/ (brew install uv)"
[[ -x "$PY" ]] || uv venv --quiet --python 3.12 "$ROOT/.venv"
uv pip install --quiet --python "$PY" -r "$ROOT/requirements.txt"
ok "$("$PY" --version), $(uv pip list --python "$PY" 2>/dev/null | wc -l | tr -d ' ') packages in .venv"
