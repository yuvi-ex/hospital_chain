#!/usr/bin/env bash
# Remove everything this project created: the console app, the Streamlit console, the HOSP_* schemas, virtual schemas,
# connections, users and role, the two branch-system containers and their data, the adapter jars in BucketFS, and the
# clock-resync loop in the VM. Left alone, because other work may use them: the JAVA and RUST script languages, the
# MongoDB adapter (MONGODB_VS), the loader's JDBC driver, the container images, .venv and .work.
#   setup/uninstall.sh --yes          database objects, containers, console, local secrets
#   setup/uninstall.sh --yes --aws    also the AWS side: the demo's S3 objects and the read-only IAM user with its key
source "$(dirname "$0")/common.sh"
export ROOT
AWS_TOO=0; [[ "${2:-}" == "--aws" ]] && AWS_TOO=1
[[ "${1:-}" == "--yes" ]] || die "this deletes the demo's database objects, containers and their data; run with --yes"

say "1. Console app on dash-server"
"$PY" - <<'PYEOF'
import json, os, sys, urllib.request
sys.path.insert(0, os.environ["ROOT"]); import hcconfig as C
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "app_delete", "arguments": {"name": C.APP, "confirmation": C.APP}}}).encode()
req = urllib.request.Request(f"http://127.0.0.1:{C.DASH_PORT}/mcp", data=body,
                             headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
try:
    raw = urllib.request.urlopen(req, timeout=120).read().decode()
    print(f"    ok  {C.APP} " + ("deleted" if '"deleted":true' in raw.replace(" ", "") else "was not there"))
except Exception as e:  # noqa: BLE001
    print(f"    skip  dash-server not reachable ({type(e).__name__})")
PYEOF
SPID=$(lsof -nP -t -iTCP:"$HC_STREAMLIT_PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)   # nothing listening is fine
# only this project's Streamlit (its working directory is our app/), never another app on the same port
if [[ -n "$SPID" ]] && lsof -a -p "$SPID" -d cwd -Fn 2>/dev/null | grep -qx "n$ROOT/app"; then kill "$SPID" && ok "Streamlit console stopped (port $HC_STREAMLIT_PORT)"
else ok "Streamlit console was not running"; fi

say "2. Database objects (HOSP_*)"
"$PY" - <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["ROOT"]); import hcconfig as C
con = C.exasol()
like = "SCHEMA_NAME LIKE 'HOSP\\_%' ESCAPE '\\'"
for (s,) in con.execute(f"SELECT SCHEMA_NAME FROM EXA_ALL_VIRTUAL_SCHEMAS WHERE {like}").fetchall():
    con.execute(f"DROP VIRTUAL SCHEMA {s} CASCADE")
for (s,) in con.execute(f"SELECT SCHEMA_NAME FROM EXA_SCHEMAS WHERE {like}").fetchall():
    con.execute(f"DROP SCHEMA {s} CASCADE")
for u in ("HOSP_DR_BRB", "HOSP_QUALITY_ANALYST"):
    con.execute(f"DROP USER IF EXISTS {u} CASCADE")
for (r,) in con.execute("SELECT ROLE_NAME FROM EXA_DBA_ROLES WHERE ROLE_NAME LIKE 'HOSP\\_%' ESCAPE '\\'").fetchall():
    con.execute(f"DROP ROLE {r} CASCADE")
for (c,) in con.execute("SELECT CONNECTION_NAME FROM EXA_DBA_CONNECTIONS WHERE CONNECTION_NAME LIKE 'HOSP\\_%' ESCAPE '\\'").fetchall():
    con.execute(f"DROP CONNECTION {c}")
left = con.execute(f"SELECT COUNT(*) FROM EXA_SCHEMAS WHERE {like}").fetchval()
print(f"    ok  HOSP_* schemas, connections, users and role removed ({left} left)")
PYEOF

say "3. Branch systems and the clock loop in the VM"
P="$HC_CONTAINER_PREFIX"
"$ROOT/setup/vm.sh" "podman rm -f $PG_CT $MONGO_CT >/dev/null 2>&1; podman volume rm $P-legacy $P-modern >/dev/null 2>&1; pkill -f '[h]c-clock-sync'; true"
ok "containers $PG_CT, $MONGO_CT and their volumes removed"
rm -rf "$BFS/default/hospital"
ok "adapter jars removed from BucketFS"
rm -f "$ROOT/secrets/agent_users.env" "$ROOT/secrets/sources.env"
ok "secrets/agent_users.env and secrets/sources.env removed"

U="$HC_CONTAINER_PREFIX-s3-reader"
if (( AWS_TOO )); then
  say "4. AWS: the demo's S3 objects and the read-only IAM user"
  export AWS_PROFILE="${HC_AWS_PROFILE:-default}"
  for d in pacs thumbs index; do aws s3 rm --recursive --only-show-errors "s3://$S3_BUCKET/${S3_PREFIX}$d/"; done
  ok "s3://$S3_BUCKET/${S3_PREFIX}{pacs,thumbs,index}/ emptied (the bucket itself is yours and stays)"
  if aws iam get-user --user-name "$U" >/dev/null 2>&1; then
    for k in $(aws iam list-access-keys --user-name "$U" --query 'AccessKeyMetadata[].AccessKeyId' --output text); do
      aws iam delete-access-key --user-name "$U" --access-key-id "$k"; done
    aws iam delete-user-policy --user-name "$U" --policy-name hc-read-only 2>/dev/null || true
    aws iam delete-user --user-name "$U"
    ok "IAM user $U, its policy and its access keys deleted"
  else ok "IAM user $U was not there"; fi
  rm -f "$S3_KEY_FILE"
  ok "local copy of the key removed ($S3_KEY_FILE)"
else
  echo
  echo "    AWS was left alone. The demo's S3 objects and the read-only IAM user $U (with an ACTIVE access key,"
  echo "    copy in $S3_KEY_FILE) still exist. Remove them with: setup/uninstall.sh --yes --aws"
fi
