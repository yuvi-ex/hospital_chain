"""Tab 3 · Who is asking: the same question through the Exasol MCP server, as two different people.

The page talks to the real exasol-mcp-server (the one an AI client such as Claude Desktop would use) over stdio, logged in
as a named database user. That user can read the governed views in HOSP_GOV and nothing else; the views filter
rows by CURRENT_USER and mask identity for an analyst. Every run is cached so a failure shows the last good run, labelled.
"""
import html as _h
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
CACHE = Path(__file__).resolve().parent / "cache"
UVX = __import__("shutil").which("uvx") or "/opt/homebrew/bin/uvx"
TIMEOUT = 30          # seconds per MCP call; the page never hangs longer than this
MCP_PKG = "exasol-mcp-server@2.2.0"
SETTINGS = {"schemas": {"like_pattern": "HOSP_GOV"}, "tables": {"enable": False}, "views": {"enable": True},
            "functions": {"enable": False}, "scripts": {"enable": False}, "enable_read_query": True,
            "enable_write_query": False, "enable_read_bucketfs": False, "enable_write_bucketfs": False,
            "enable_preprocessor_tools": False, "default_row_limit": 50}

PEOPLE = {
    "HOSP_DR_BRB": ("Treating physician, Branch B", "own branch's patients, full identity"),
    "HOSP_QUALITY_ANALYST": ("Quality analyst, all branches", "every branch, identities masked"),
}
QUESTION = "Which patients have a current order that conflicts with a recorded allergy?"
SQL_TOP = """SELECT PATIENT_NAME, DRUG, ORDER_STATUS, ALLERGY_AS_RECORDED, ALLERGY_RECORDED_IN, KNOWN_WHERE_PRESCRIBED,
       COUNT(*) OVER () AS ALERTS                               -- total for this person, same pass
FROM   HOSP_GOV.ALLERGY_ALERTS                                 -- the certified safety check: one row per conflicting order
ORDER  BY KNOWN_WHERE_PRESCRIBED, PATIENT_NAME"""
SQL_BYPASS = "SELECT * FROM HOSP_CORE.PATIENT_SUMMARY LIMIT 5   -- the raw identities behind the views"
SQL_AUDIT = """SELECT s.USER_NAME, a.START_TIME, a.SUCCESS, ROUND(a.DURATION, 2) AS SECS,
       SUBSTR(a.SQL_TEXT, 1, 70) AS SQL_TEXT
FROM   EXA_DBA_AUDIT_SQL a
JOIN   EXA_DBA_AUDIT_SESSIONS s ON s.SESSION_ID = a.SESSION_ID
WHERE  s.USER_NAME LIKE 'HOSP_%' AND a.COMMAND_NAME = 'SELECT'
  AND  a.SQL_TEXT NOT LIKE '/*snapshot execution*/%'
ORDER  BY a.START_TIME DESC LIMIT 8"""


class Mcp:
    """A minimal MCP client over stdio: initialize, then tools/call."""

    def __init__(self, user):
        pw = dict(l.strip().split("=", 1) for l in open(HOME / "secrets" / "agent_users.env") if "=" in l)
        # the local Exasol Personal endpoint; nocertcheck because the kit uses a self-signed certificate
        env = dict(os.environ, EXA_DSN=__import__("hcconfig").EXA_DSN, EXA_USER=user,
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


# ------------------------------------------------------------------ rendering
CSS = """<style>
.ag-flow { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.6rem; margin:.4rem 0 1rem; }
.ag-box { border-radius:14px; border:1.5px solid var(--edge); background:#fff; padding:.7rem .85rem; position:relative; }
.ag-box.on { border-color:#12796A; background:#F2FBF9; }
.ag-box .h { font-weight:800; font-size:1rem; } .ag-box .s { font-size:.78rem; color:var(--teal-ink); font-weight:700; margin:.1rem 0 .3rem; }
.ag-box .d { font-size:.82rem; color:var(--muted); line-height:1.4; }
.ag-box:not(:last-child)::after { content:"→"; position:absolute; right:-.62rem; top:42%; color:#12796A; font-weight:900; }
.ag-who { border-radius:14px; background:#0B3D5C; color:#fff; padding:.7rem 1rem; margin:.2rem 0 .8rem; }
.ag-who b { color:#7FE3D0; } .ag-who .u { font-family:'JetBrains Mono',monospace; font-size:.8rem; opacity:.85; }
.ag-step { display:grid; grid-template-columns:2rem 1fr auto; gap:.6rem; align-items:start; border-top:1px dashed var(--edge); padding:.45rem 0; font-size:.86rem; }
.ag-step .k { width:1.6rem; height:1.6rem; border-radius:50%; background:#12796A; color:#fff; font-weight:800; font-size:.8rem; display:flex; align-items:center; justify-content:center; }
.ag-step .k.bad { background:#B42318; }
.ag-step code { font-size:.78rem; } .ag-step .t { color:var(--faint); font-size:.75rem; white-space:nowrap; }
.ag-def { background:#EEF2FF; border:1px solid #C7D2FE; border-radius:10px; padding:.35rem .6rem; margin-top:.3rem; font-size:.8rem; color:#3730A3; }
.ag-cmp { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; margin:.6rem 0; }
.ag-cmp .c { border-radius:14px; border:1px solid var(--edge); background:#fff; padding:.6rem .8rem; }
.ag-cmp .c .v { font-size:1.4rem; font-weight:900; color:#0B3D5C; } .ag-cmp .c .l { font-size:.8rem; color:var(--muted); }
.ag-no { border-radius:12px; background:#FEF3F2; border:1px solid #FECDCA; color:#912018; padding:.55rem .8rem; font-size:.88rem; margin:.4rem 0; }
.ag-aud table { width:100%; border-collapse:collapse; font-size:.8rem; } .ag-aud td, .ag-aud th { border-bottom:1px solid var(--edge); padding:.3rem .4rem; text-align:left; }
.ag-aud .f { color:#B42318; font-weight:800; } .ag-aud .ok { color:#12796A; font-weight:800; }
@media (max-width:1100px) { .ag-flow { grid-template-columns:repeat(2,minmax(0,1fr)); } .ag-box::after { display:none; } }
</style>"""


def flow(user, lit):
    who = PEOPLE[user][0]
    boxes = [("AI client", "Claude, a hospital assistant, an IDE", f"Asks on behalf of a person: {who}."),
             ("Exasol MCP server", f"logged in as {user}", "Read-only tools. It lists what this person may see and runs the SQL as them."),
             ("Exasol engine", "role · governed view · masking", "The row filter and the masking apply before anything leaves. The sources are read live."),
             ("Answer", "with the SQL that produced it", "Re-run the SQL next week, as the same person, and get the same number.")]
    return '<div class="ag-flow">' + "".join(
        f'<div class="ag-box{" on" if lit else ""}"><div class="h">{h}</div><div class="s">{_h.escape(s)}</div><div class="d">{_h.escape(d)}</div></div>'
        for h, s, d in boxes) + "</div>"


def steps_html(out):
    labels = ["Which data may I see?", "Which governed views are there, and what do they mean?",
              "Run the question against the certified view, as this person"]
    h = ""
    for i, s in enumerate(out.get("steps", [])):
        body = f'<code>{_h.escape(s["tool"])}</code> &middot; {labels[i] if i < len(labels) else ""}'
        if i == 0:
            names = [x.get("name") for x in ((s.get("data") or {}).get("result") or [])]
            body += f'<div class="d">Schemas this person can see: <b>{_h.escape(", ".join(names) or "none")}</b></div>'
        elif i == 1:
            for v in ((s.get("data") or {}).get("result") or []):
                if v.get("name") == "ALLERGY_ALERTS":
                    body += f'<div class="ag-def"><b>{v["name"]}</b>: {_h.escape(v.get("comment") or "")}</div>'
            names = [v.get("name") for v in ((s.get("data") or {}).get("result") or [])]
            body += f'<div class="d" style="margin-top:.2rem">Views: {_h.escape(", ".join(names))}</div>'
        h += f'<div class="ag-step"><div class="k">{i + 1}</div><div>{body}</div><div class="t">{s.get("secs", 0):.1f} s</div></div>'
    return h


def answer_html(out, big3):
    top = out.get("top") or []
    alerts = int((top[0] if top else {}).get("ALERTS") or 0)
    named = sum(1 for r in top if not str(r.get("PATIENT_NAME", "")).startswith("Patient "))
    hidden = sum(1 for r in top if str(r.get("KNOWN_WHERE_PRESCRIBED")).lower() == "false")
    nums = [(f"{alerts}", "conflicting orders this person may see", True),
            (f"{named} named", f"{len(top) - named} masked: identity as this person is allowed", False),
            (f"{hidden}", "of these allergies are missing from the system that wrote the order", False)]
    rows = "".join(f'<div class="cu"><div><div class="nm">{_h.escape(str(r["PATIENT_NAME"]))} &middot; {_h.escape(str(r["DRUG"]))} ({_h.escape(str(r["ORDER_STATUS"]))})</div>'
                   f'<div class="mt" style="font-style:normal">&ldquo;{_h.escape(str(r["ALLERGY_AS_RECORDED"]))}&rdquo; in the '
                   f'{"legacy HIS" if r["ALLERGY_RECORDED_IN"] == "LEGACY_HIS" else "EHR"}'
                   + (' &middot; <b style="color:#C8102E">no allergy on file in the system that wrote the order</b>' if str(r["KNOWN_WHERE_PRESCRIBED"]).lower() == "false" else ' &middot; <b style="color:#12796A">allergy on file where prescribed</b>') + '</div></div></div>'
for r in top)
    return big3(nums) + rows
