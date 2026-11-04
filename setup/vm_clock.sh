#!/usr/bin/env bash
# Keep the Exasol VM's clock right. It runs slow (about 50 min lost in 30 min on 2026-10-28) and the VM has no
# internet for NTP, so S3 starts refusing Exasol's signed requests (403 RequestTimeTooSkewed) and the PACS pill goes red.
# The hypervisor's real-time clock is correct: copy it into the system clock every 30 s. Idempotent; gone after a VM
# restart, so preflight.sh runs this again.
source "$(dirname "$0")/common.sh"
# The [w] keeps pgrep from matching the ssh shell that runs this check (it did, and reported a dead loop as running).
# setsid (BusyBox: no -f) detaches the loop from the ssh session, so it survives the session closing.
# The loop's name is assembled from $N at run time: written out literally, it would sit in this ssh shell's own command
# line, pgrep would find the shell, and the loop would never start.
"$ROOT/setup/vm.sh" 'hwclock -s; N=hc-clock; pgrep -f "[h]c-clock-sync" >/dev/null || setsid sh -c "while :; do hwclock -s; sleep 30; done" "$N-sync" </dev/null >/dev/null 2>&1 &'
sleep 1
ok "VM clock synced, resync loop $("$ROOT/setup/vm.sh" 'pgrep -f "[h]c-clock-sync" >/dev/null && echo running || echo NOT running'), skew $(( $(date +%s) - $("$ROOT/setup/vm.sh" 'date +%s') ))s"
