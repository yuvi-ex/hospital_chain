#!/usr/bin/env bash
# Start the two branch systems in podman INSIDE the Exasol Personal VM.
#   <prefix>-legacy-pg     Postgres 16  (legacy HIS)   VM port HC_PG_PORT    (default 55432)
#   <prefix>-modern-mongo  MongoDB 8.2  (modern EHR)   VM port HC_MONGO_PORT (default 37017)
# Why inside the VM, not Docker on the Mac: a managed-Mac firewall can block INBOUND connections to every app, so the VM
# cannot reach Docker-published ports (TCP connects, then is cut: "EOF"/"Empty reply"). In the VM's own podman the
# database reaches them over the podman bridge, and the Mac reaches them outbound on the VM's IP.
# The VM has no internet and no systemd: images are streamed in from Docker once, and this script must be
# re-run after the VM restarts (preflight does it). Idempotent.
source "$(dirname "$0")/common.sh"
VM="$ROOT/setup/vm.sh"
P="$HC_CONTAINER_PREFIX"

say "1. Images in the VM"
if ! "$VM" 'podman image exists localhost/postgres:16 && podman image exists localhost/mongo:8.2'; then
  docker pull -q postgres:16 >/dev/null && docker pull -q mongo:8.2 >/dev/null   # NOT mongo 8.0/latest: no boot on kernel >= 6.19
  docker save postgres:16 mongo:8.2 | "$VM" 'podman load' | tail -2
fi
ok "postgres:16, mongo:8.2"

say "2. Containers"
"$VM" "
podman volume exists $P-legacy || podman volume create $P-legacy >/dev/null
podman volume exists $P-modern || podman volume create $P-modern >/dev/null
podman container exists $PG_CT || podman create --name $PG_CT --restart always \
  -e POSTGRES_USER=his_admin -e POSTGRES_PASSWORD=$HC_PG_ADMIN_PASSWORD -e POSTGRES_DB=branch_a_his \
  -p $PG_PORT:5432 -v $P-legacy:/var/lib/postgresql/data localhost/postgres:16 >/dev/null
podman container exists $MONGO_CT || podman create --name $MONGO_CT --restart always \
  -e MONGO_INITDB_ROOT_USERNAME=root -e MONGO_INITDB_ROOT_PASSWORD=$HC_MONGO_ROOT_PASSWORD \
  -p $MONGO_PORT:27017 -v $P-modern:/data/db localhost/mongo:8.2 >/dev/null
podman start $PG_CT $MONGO_CT >/dev/null
podman ps --filter name=$P- --format '{{.Names}}  {{.Status}}  {{.Ports}}'"
