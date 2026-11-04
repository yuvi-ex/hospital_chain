# shellcheck shell=bash disable=SC2034  # sourced: the variables below are used by the scripts that source it
# Shared settings for the hospital-chain demo setup scripts. Source it, do not run it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/.work"; mkdir -p "$WORK"
# config.local.env (your overrides, git-ignored) wins over config.env; an environment variable of the same name wins over both
for f in "$ROOT/config.local.env" "$ROOT/config.env"; do
  [[ -f "$f" ]] || continue
  while IFS='=' read -r k v; do
    [[ -z "$k" || "$k" == \#* ]] && continue
    v="${v%$'\r'}"; v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"     # same rules as hcconfig.py: no CR, no quotes
    [[ -n "${!k:-}" ]] || export "$k=$v"
  done < "$f"
done
# Passwords of the two branch systems (Postgres admin + read-only login, MongoDB root + read-only login): generated
# once into secrets/sources.env (git-ignored, mode 600), never written in code. setup/uninstall.sh deletes the file
# together with the container volumes they belong to.
SOURCES_ENV="$ROOT/secrets/sources.env"
if [[ ! -f "$SOURCES_ENV" ]]; then
  (umask 077; mkdir -p "$ROOT/secrets"; python3 -c 'import secrets
for k in ("HC_PG_ADMIN_PASSWORD", "HC_PG_READER_PASSWORD", "HC_MONGO_ROOT_PASSWORD", "HC_MONGO_READER_PASSWORD"):
    print(f"{k}={secrets.token_hex(16)}")' >"$SOURCES_ENV")
fi
set -a
# shellcheck source=/dev/null
source "$SOURCES_ENV"
set +a
DEPLOY_DIR="$HOME/.exasol/personal/deployments/default"
# BucketFS on this Personal build is a directory shared with the Mac: an upload is a copy,
# and the engine reconciles it into a bucket within about a second. Buckets start empty.
BFS="$DEPLOY_DIR/local/runtime/vm-shared/exa/bucketfs/bfsdefault"
# The address the Exasol DB container uses to reach the sibling containers in the VM: the podman bridge gateway.
SRC_HOST="${SRC_HOST:-10.88.0.1}"
S3_BUCKET="$HC_S3_BUCKET"
S3_REGION="$HC_S3_REGION"
S3_PREFIX="${HC_S3_PREFIX:-}"
S3_KEY_FILE="$HC_S3_KEY_FILE"; [[ "$S3_KEY_FILE" == /* ]] || S3_KEY_FILE="$ROOT/$S3_KEY_FILE"
PG_CT="$HC_CONTAINER_PREFIX-legacy-pg"; MONGO_CT="$HC_CONTAINER_PREFIX-modern-mongo"
PG_PORT="$HC_PG_PORT"; MONGO_PORT="$HC_MONGO_PORT"
PY="$ROOT/.venv/bin/python"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()  { printf '    \033[0;32mok\033[0m  %s\n' "$*"; }
die() { printf '\n\033[0;31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# exasol connect prints CSV (a header row per statement) on stdout and exits 1 on a SQL error.
# -k: accept the self-signed certificate of Exasol Personal on this machine. Do not copy -k to scripts that talk to a
# real Exasol cluster: let the CLI verify the certificate there.
xsql()  { exasol connect -k --csv -c "$1" 2>/dev/null; }
# run a SQL file; on the first error print it and fail (the calling script stops: set -e)
xfile() {
  exasol connect -k --csv -f "$1" >/dev/null 2>"$WORK/sql.err" && return 0
  grep -v '^Using default deployment' "$WORK/sql.err" | sed 's/^/    /' >&2
  printf '\033[0;31mSQL failed in %s\033[0m\n' "$1" >&2
  return 1
}
