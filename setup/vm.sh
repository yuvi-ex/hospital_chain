#!/usr/bin/env bash
# Run a command inside the Exasol Personal VM (root). Usage: setup/vm.sh '<command>'
K="$HOME/.exasol/personal/deployments/default/local/runtime/vm-ssh-key"
IP="$(python3 -c "import json;print(json.load(open('$HOME/.exasol/personal/deployments/default/local/runtime/vm-runtime.json'))['vm_ip'])")"
exec ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 -i "$K" "root@$IP" "$@"
