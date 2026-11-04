"""Settings for the Python side of the demo: config.env at the repository root, overridden by environment variables.

    import hcconfig as C;  C.S3_BUCKET, C.ROOT, C.exasol() ...
"""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load():
    """config.env, then config.local.env (your overrides, git-ignored), then environment variables."""
    vals = {}
    # secrets/sources.env holds the generated branch-system passwords (setup/common.sh writes it on the first step)
    for f in (ROOT / "config.env", ROOT / "config.local.env", ROOT / "secrets" / "sources.env"):
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    vals.update({k: v for k, v in os.environ.items() if k.startswith("HC_")})
    return vals


_V = _load()


def _path(v):
    p = Path(v).expanduser()
    return p if p.is_absolute() else ROOT / p


S3_BUCKET, S3_REGION, S3_PREFIX = _V["HC_S3_BUCKET"], _V["HC_S3_REGION"], _V.get("HC_S3_PREFIX", "")
AWS_PROFILE = _V.get("HC_AWS_PROFILE") or None
S3_KEY_FILE = _path(_V["HC_S3_KEY_FILE"])
CONTAINER_PREFIX = _V["HC_CONTAINER_PREFIX"]
PG_PORT, MONGO_PORT = int(_V["HC_PG_PORT"]), int(_V["HC_MONGO_PORT"])
EXAPUMP_PROFILE = _V["HC_EXAPUMP_PROFILE"]
EXA_DSN = _V["HC_EXA_DSN"]
APP, DASH_PORT, DASH_PROFILE = _V["HC_APP"], int(_V["HC_DASH_PORT"]), _V["HC_DASH_PROFILE"]
STREAMLIT_PORT = int(_V["HC_STREAMLIT_PORT"])
PY = ROOT / ".venv" / "bin" / "python"
AGENT_USERS = ROOT / "secrets" / "agent_users.env"
VM_RUNTIME = Path.home() / ".exasol" / "personal" / "deployments" / "default" / "local" / "runtime"


def secret(name):
    """A generated branch-system password (secrets/sources.env), with a message that says how to create it."""
    if name not in _V:
        raise SystemExit(f"{name} missing from secrets/sources.env: run setup/build_all.sh (its first steps create it)")
    return _V[name]


def vm_ip():
    import json
    return json.loads((VM_RUNTIME / "vm-runtime.json").read_text())["vm_ip"]


def exasol(**kw):
    """An admin session from the exapump profile.

    TLS is on but the certificate is not verified: Exasol Personal serves a self-signed certificate on this machine.
    Against a real Exasol cluster, verify it (pyexasol: dsn="host/<FINGERPRINT>:8563", or a CA bundle)."""
    import pyexasol
    c = tomllib.load(open(Path.home() / ".exapump" / "config.toml", "rb"))[EXAPUMP_PROFILE]
    return pyexasol.connect(dsn=f"{c['host']}:{c['port']}", user=c["user"], password=c["password"],
                            encryption=True, websocket_sslopt={"cert_reqs": 0}, **kw)
