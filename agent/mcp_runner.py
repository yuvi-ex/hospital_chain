#!/usr/bin/env python3
"""The agent side of tab 3: the real exasol-mcp-server, started over stdio as a named database user.

Runs OUTSIDE the dash-server app on purpose. dash-server refuses hosted apps that handle Exasol credentials, and this
is exactly the part that must: it logs in as HOSP_DR_BRB or HOSP_QUALITY_ANALYST (passwords in
secrets/agent_users.env, mode 600, never printed), the way Claude Desktop would start the same server. The console
calls this script and only ever sees the JSON answer.

    .venv/bin/python agent/mcp_runner.py ask HOSP_DR_BRB
    .venv/bin/python agent/mcp_runner.py bypass HOSP_QUALITY_ANALYST
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
import hcconfig  # noqa: E402

CACHE = HOME / "dash" / "cache"
UVX = shutil.which("uvx") or "/opt/homebrew/bin/uvx"
TIMEOUT = 30          # seconds per MCP call; the page never hangs longer than this
MCP_PKG = "exasol-mcp-server@2.2.0"
SETTINGS = {"schemas": {"like_pattern": "HOSP_GOV"}, "tables": {"enable": False}, "views": {"enable": True},
            "functions": {"enable": False}, "scripts": {"enable": False}, "enable_read_query": True,
            "enable_write_query": False, "enable_read_bucketfs": False, "enable_write_bucketfs": False,
            "enable_preprocessor_tools": False, "default_row_limit": 50}
sys.path.insert(0, str(HOME / "dash"))
from agent_tab import SQL_BYPASS, SQL_TOP  # noqa: E402  the SQL is defined once, beside the page that shows it


class Mcp:
    """A minimal MCP client over stdio: initialize, then tools/call."""

    def __init__(self, user):
        pw = dict(l.strip().split("=", 1) for l in open(HOME / "secrets" / "agent_users.env") if "=" in l)
        # the local Exasol Personal endpoint; nocertcheck because the kit uses a self-signed certificate
        env = dict(os.environ, EXA_DSN=hcconfig.EXA_DSN, EXA_USER=user,
                   EXA_PASSWORD=pw[user], EXA_MCP_SETTINGS=json.dumps(SETTINGS))
        self.p = subprocess.Popen([UVX, MCP_PKG], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=env, text=True, bufsize=1)
        self.n = 0
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "hospital-chain-demo", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(line)
        self.q.put(None)

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def _rpc(self, method, params):
        self.n += 1
        self._send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        deadline = time.time() + TIMEOUT
        while True:
            try:
                line = self.q.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                raise ConnectionError("No answer from the database within 30 s (is Exasol running? exakit status)")
            if line is None:
                raise ConnectionError("The MCP server stopped (is Exasol running? exakit status)")
            msg = json.loads(line)
            if msg.get("id") == self.n:
                return msg

    def call(self, tool, args):
        t = time.time()
        r = self._rpc("tools/call", {"name": tool, "arguments": args})
        res = r.get("result") or {}
        text = "".join(c.get("text", "") for c in res.get("content", []))
        data = res.get("structuredContent")
        return {"tool": tool, "args": args, "error": bool(res.get("isError")) or "error" in r,
                "text": text, "data": data, "secs": time.time() - t}

    def close(self):
        try:
            self.p.terminate()
        except Exception:  # noqa: BLE001
            pass


def _rows(step):
    d = step.get("data") or {}
    cols, rows = d.get("columns") or [], d.get("rows") or []
    return [dict(zip(cols, r)) for r in rows]


def ask(user):
    """The agent path: discover, read the definition, query. Returns steps + answer; cached per user."""
    t0 = time.time()
    m = Mcp(user)
    try:
        steps = [m.call("list_exasol_schemas", {}),
                 m.call("list_exasol_tables_and_views", {"schema_name": "HOSP_GOV"}),
                 m.call("execute_exasol_query", {"query": SQL_TOP})]
    finally:
        m.close()
    out = {"user": user, "steps": steps, "top": _rows(steps[2]), "total": (_rows(steps[2]) or [{}])[0],
           "secs": time.time() - t0, "at": time.strftime("%H:%M:%S"), "live": True}
    if not any(s["error"] for s in steps):
        CACHE.mkdir(exist_ok=True)
        (CACHE / f"agent_{user}.json").write_text(json.dumps(out, default=str))
        return out
    raise RuntimeError(next(s["text"] for s in steps if s["error"])[:300])


def ask_or_cached(user):
    try:
        try:
            return ask(user)
        except Exception:  # noqa: BLE001 - one retry: a flaky network or a new IP on the first connect
            return ask(user)
    except Exception as e:  # noqa: BLE001
        f = CACHE / f"agent_{user}.json"
        if f.exists():
            out = json.loads(f.read_text())
            out.update(live=False, error=str(e)[:300])
            return out
        return {"user": user, "steps": [], "top": [], "total": {}, "live": False, "error": str(e)[:300]}


def _bypass_once(user):
    m = Mcp(user)
    try:
        return m.call("execute_exasol_query", {"query": SQL_BYPASS})
    finally:
        m.close()


def bypass(user):
    """Ask for the raw table. Retry once if the error is not a privilege refusal (network, new IP)."""
    try:
        r = _bypass_once(user)
    except Exception as e:  # noqa: BLE001
        r = {"error": True, "text": str(e), "secs": 0}
    if "privilege" not in r.get("text", "").lower():
        try:
            r = _bypass_once(user)
        except Exception as e:  # noqa: BLE001
            r = {"error": True, "text": str(e), "secs": 0}
    return r

if __name__ == "__main__":
    cmd, user = sys.argv[1], sys.argv[2]
    out = ask_or_cached(user) if cmd == "ask" else bypass(user)
    print(json.dumps(out, default=str))
