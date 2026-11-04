#!/usr/bin/env bash
# Install the MongoDB virtual schema adapter (exasol-labs/exasol-mongodb-vs) on Exasol Personal.
# The vendor SLC installer needs an SSH port this Personal build no longer exposes; BucketFS is a
# directory shared with the Mac, so the install is: copy the Rust SLC + adapter, register RUST, create 2 scripts.
# Idempotent.
source "$(dirname "$0")/common.sh"

SLC_VERSION=0.23.0
ARCH="$(uname -m)"; [[ "$ARCH" == arm64 || "$ARCH" == aarch64 ]] && SLC_ARCH="-aarch64" || SLC_ARCH=""
SLC_TGZ="${SLC_TGZ:-$WORK/lc-rust-$SLC_VERSION$SLC_ARCH.tar.gz}"
VS_REPO="${VS_REPO:-$WORK/exasol-mongodb-vs}"
VS_COMMIT="${VS_COMMIT:-aa3e217}"   # the adapter version this demo was built and tested with
SO="${SO:-$WORK/libmongodb_vs.so}"
RUST_DEF="RUST=localzmq+protobuf:///bfsdefault/default/slc/rustslc?lang=rust#buckets/bfsdefault/default/slc/rustslc/exaudf/exaudfclient"

say "0. Download what is missing (Rust SLC ~200 MB; adapter built in Docker, ~3 min the first time)"
[[ -s "$SLC_TGZ" ]] || curl -fsSL -o "$SLC_TGZ" \
  "https://github.com/exasol-labs/language-container-rs/releases/download/v$SLC_VERSION/lc-rust-$SLC_VERSION$SLC_ARCH.tar.gz"
if [[ ! -f "$SO" ]]; then
  [[ -d "$VS_REPO/.git" ]] || git clone --quiet https://github.com/exasol-labs/exasol-mongodb-vs.git "$VS_REPO"
  git -C "$VS_REPO" -c advice.detachedHead=false checkout --quiet "$VS_COMMIT"
  # Build a Linux .so inside a Rust container (a macOS build is not loadable). The source is copied INTO the container and
  # compiled there: building in a folder shared with the Mac (as the repo's `make build-so` does) loses files mid-build on
  # Docker Desktop and fails with "can't find crate for ...".
  docker run --rm -v "$VS_REPO:/src:ro" -v "$WORK:/out" rust:1.94.1-trixie bash -c \
    'apt-get update -qq >/dev/null && apt-get install -y -qq protobuf-compiler pkg-config cmake >/dev/null 2>&1 &&
     cp -r /src /build && rm -rf /build/target && cd /build && cargo build --quiet --locked --release -p mongodb-vs &&
     cp target/release/libmongodb_vs.so /out/ && chown '"$(id -u):$(id -g)"' /out/libmongodb_vs.so'
  file "$SO" | grep -q "ELF 64-bit LSB shared object" || die "adapter build did not produce a Linux .so"
fi
ok "$(basename "$SLC_TGZ"), $(basename "$SO")"

say "1. Rust script-language container + adapter into BucketFS"
mkdir -p "$BFS/default/slc/rustslc" "$BFS/rust"
[[ -x "$BFS/default/slc/rustslc/exaudf/exaudfclient" ]] || tar xzf "$SLC_TGZ" -C "$BFS/default/slc/rustslc"
# an adapter already in BucketFS is left alone (other schemas may use it); FORCE=1 replaces it
[[ -f "$BFS/rust/libmongodb_vs.so" && -z "${FORCE:-}" ]] || cp "$SO" "$BFS/rust/libmongodb_vs.so"
sleep 3
ok "SLC + $(ls -lh "$BFS/rust/libmongodb_vs.so" | awk '{print $5}') adapter in place"

say "2. Register RUST (other languages left as they are)"
CUR=$(xsql "SELECT SYSTEM_VALUE FROM EXA_PARAMETERS WHERE PARAMETER_NAME='SCRIPT_LANGUAGES';" | tail -1)
if [[ "$CUR" == *"$RUST_DEF"* ]]; then ok "already registered"; else
  NEW=$(echo "$CUR $RUST_DEF" | awk '{sep=""; for(i=1;i<=NF;i++){if($i ~ /^RUST=/ && i<NF) continue; printf "%s%s",sep,$i; sep=" "}}')
  xsql "ALTER SYSTEM SET SCRIPT_LANGUAGES = '$NEW';" >/dev/null
  ok "$(echo "$NEW" | tr ' ' '\n' | cut -d= -f1 | tr '\n' ' ')"
fi

say "3. Adapter + scan scripts"
if [[ "$(xsql "SELECT COUNT(*) FROM EXA_ALL_SCRIPTS WHERE SCRIPT_SCHEMA='MONGODB_VS';" | tail -1)" -ge 2 ]]; then
  ok "already installed (left as it is)"
else
  xfile "$VS_REPO/sql/install.sql"
fi
xsql "SELECT SCRIPT_NAME, SCRIPT_LANGUAGE FROM EXA_ALL_SCRIPTS WHERE SCRIPT_SCHEMA='MONGODB_VS';"
