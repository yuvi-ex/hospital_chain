#!/usr/bin/env bash
# Build the whole demo from a fresh clone, in order. Every step is re-runnable; a failed step stops the build.
#   setup/build_all.sh            all steps
#   setup/build_all.sh 6          from step 6 on (after fixing what stopped step 6)
# Needs: Exasol Personal running (exakit / exasol CLI), Docker (images and the adapter build), uv, the AWS CLI with a
# profile that can write to your bucket and create one IAM user, and HC_S3_BUCKET set in config.local.env.
source "$(dirname "$0")/common.sh"
FROM="${1:-0}"
step() { local n="$1"; shift; (( n >= FROM )) || return 1; say "STEP $n · $*"; }
sqlf() {  # run a SQL file; stop on the first error
  exasol connect -k --csv -f "$1" >/dev/null 2>"$WORK/sql.err" || { grep -v '^Using default deployment' "$WORK/sql.err" >&2; die "SQL failed in $1"; }
  ok "$(basename "$1")"
}

[[ "$S3_BUCKET" != your-bucket-name ]] || die "set HC_S3_BUCKET in config.local.env (an S3 bucket you own) first: see README, Install"
xsql "SELECT 1;" | grep -q 1 || die "Exasol does not answer: exakit start"

if step 0 "Python environment"; then "$ROOT/setup/venv.sh"; fi
if step 1 "Branch systems: Postgres + MongoDB inside the Exasol VM"; then "$ROOT/setup/00_sources_vm.sh"; fi
if step 2 "Script languages: Java (Postgres adapter) and Rust (MongoDB adapter)"; then
  if xsql "SELECT SYSTEM_VALUE FROM EXA_PARAMETERS WHERE PARAMETER_NAME='SCRIPT_LANGUAGES';" | grep -q 'JAVA='; then ok "JAVA registered"
  else exasol slc install JAVA --auto-approve; fi            # restarts the database
  "$ROOT/setup/01_mongo_vs.sh"
fi
if step 3 "Generate the hospital chain into both systems (seeded; also writes data/out)"; then
  for _ in $(seq 1 30); do "$PY" -c "
import sys, psycopg, pymongo; sys.path.insert(0, '$ROOT'); import hcconfig as C
psycopg.connect(host=C.vm_ip(), port=C.PG_PORT, user='his_admin', password=C.secret('HC_PG_ADMIN_PASSWORD'), dbname='branch_a_his', connect_timeout=3).close()
pymongo.MongoClient(C.vm_ip(), C.MONGO_PORT, username='root', password=C.secret('HC_MONGO_ROOT_PASSWORD'), authSource='admin', directConnection=True, serverSelectionTimeoutMS=3000).admin.command('ping')" 2>/dev/null && break; sleep 2; done
  "$PY" "$ROOT/data/generate.py"
fi
if step 4 "Attach the sources: connections + virtual schemas"; then "$ROOT/setup/02_sources.sh"; fi
if step 5 "Note vectors"; then "$PY" "$ROOT/data/embed.py"; fi
if step 6 "Typed views + patient index"; then
  sqlf "$ROOT/sql/10_typed_sources.sql"; sqlf "$ROOT/sql/20_mpi.sql"; "$PY" "$ROOT/data/check_mpi.py"
fi
if step 7 "Imaging archive on S3"; then
  "$PY" "$ROOT/data/imaging.py" upload
  [[ -s "$S3_KEY_FILE" ]] || "$ROOT/setup/s3_reader.sh"
  sleep 10                                                    # a new IAM key takes a few seconds to work
  "$PY" "$ROOT/data/imaging.py" verify
  "$ROOT/setup/vm_clock.sh"                                    # S3 refuses requests signed with a wrong VM clock
  "$ROOT/setup/04_imaging.sh"
fi
if step 8 "Clinical views, governance, acceleration, console view"; then
  sqlf "$ROOT/sql/30_fused.sql"
  "$PY" "$ROOT/setup/05_governance.py"
  sqlf "$ROOT/sql/50_accelerate.sql"; sqlf "$ROOT/sql/60_console.sql"
fi
if step 9 "Console on dash-server"; then "$PY" "$ROOT/dash/deploy.py"; fi
if step 10 "Preflight"; then "$ROOT/setup/preflight.sh"; fi
