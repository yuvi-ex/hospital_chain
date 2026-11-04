#!/usr/bin/env bash
# Demo-day check: GO / NO-GO, and it fixes what it safely can. Run it before every demo:
#   setup/preflight.sh
# Self-heals: starts Exasol, starts the two containers inside the VM (they do not survive a VM restart),
# resyncs the VM clock (S3 requests are signed with it; after the Mac sleeps it freezes and S3 answers 403,
# which looks exactly like bad credentials). Then proves each source answers with a real query.
source "$(dirname "$0")/common.sh"
FAIL=0
bad() { printf '    \033[0;31mNO\033[0m  %s\n' "$*"; FAIL=1; }

say "1. Exasol"
exakit status 2>/dev/null | grep -q "personal · running" || exakit start >/dev/null 2>&1 || true
xsql "SELECT 1;" | grep -q 1 && ok "database answers" || bad "database not reachable: exakit start"

say "2. Branch systems inside the VM"
"$ROOT/setup/vm.sh" "podman start $PG_CT $MONGO_CT >/dev/null 2>&1; podman ps --filter name=$HC_CONTAINER_PREFIX- --format '{{.Names}} {{.Status}}'" \
  | sed 's/^/    /'

say "3. VM clock (S3 signs with it; it runs slow, so a resync loop runs inside the VM)"
"$ROOT/setup/vm_clock.sh" >/dev/null
SKEW=$(( $(date +%s) - $("$ROOT/setup/vm.sh" 'date +%s') ))
LOOP=$("$ROOT/setup/vm.sh" 'pgrep -f "[h]c-clock-sync" >/dev/null && echo yes || echo no')
(( SKEW <= 60 && SKEW >= -60 )) && [[ "$LOOP" == yes ]] && ok "skew ${SKEW}s, resync loop running" || bad "VM clock ${SKEW}s off (loop: $LOOP): S3 will answer 403"

say "4. Each source, through Exasol"
sleep 3
check() { local n; n=$(xsql "$2" | tail -1); if [[ "$n" =~ ^[0-9]+$ && "$n" -gt 0 ]]; then ok "$1: $n"; else bad "$1: $(exasol connect -k --csv -c "$2" 2>&1 | grep -i error | cut -c1-160)"; fi; }
check "legacy HIS (Postgres), patients"     "SELECT COUNT(*) FROM HOSP_LEGACY.PAT_MSTR;"
check "modern EHR (MongoDB), hero record"   "SELECT COUNT(*) FROM HOSP_SRC.MODERN_PATIENTS WHERE RECORD_ID='BRB-P-108842' GROUP BY RECORD_ID;"
check "PACS (S3), studies"                  "SELECT COUNT(*) FROM HOSP_SRC.IMAGING_INDEX GROUP BY 'x';"
check "hero allergy conflict"               "SELECT COUNT(*) FROM HOSP_CORE.ALLERGY_CONFLICTS WHERE PRESCRIBED_UNDER='BRB-P-108842' GROUP BY PRESCRIBED_UNDER;"
check "free sessions (cap is 20)"           "SELECT 20 - COUNT(*) FROM EXA_DBA_SESSIONS GROUP BY 'x';"

say "5. Consoles"
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$HC_DASH_PORT/apps/$HC_APP/ | grep -q 200 \
  && ok "dash-server http://127.0.0.1:$HC_DASH_PORT/apps/$HC_APP" \
  || bad "dash-server console not answering: exakit stop dash-server && exakit start dash-server"
# the Streamlit fallback is optional and never started here (another app may own its port): start it with app/run.sh
printf '    \033[0;33mnote\033[0m  fallback console (optional): app/run.sh -> http://localhost:%s\n' "$HC_STREAMLIT_PORT"

echo
(( FAIL == 0 )) && printf '\033[1;32mGO\033[0m\n' || { printf '\033[1;31mNO-GO\033[0m (fix the NO lines above)\n'; exit 1; }
