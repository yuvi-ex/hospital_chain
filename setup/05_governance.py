#!/usr/bin/env python3
"""Governed views + the two named people who query them (directly or through an AI client over MCP).
  HOSP_DR_BRB           treating physician, Branch B   FULL identity, own branch's patients
  HOSP_QUALITY_ANALYST  quality analyst, all branches   MASKED identity
Passwords are generated once into secrets/agent_users.env (mode 600) and never printed.
  .venv/bin/python setup/05_governance.py
"""
import os
import secrets
import sys
from pathlib import Path

import pyexasol

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "secrets" / "agent_users.env"
USERS = ["HOSP_DR_BRB", "HOSP_QUALITY_ANALYST"]


def statements(path):
    """';'-terminated statements; comment-only lines skipped. (No scripts in these files.)"""
    out, buf = [], []
    for line in open(path):
        s = line.strip()
        if not buf and (not s or s.startswith("--")):
            continue
        buf.append(line)
        code = s.split("--", 1)[0].rstrip()          # a trailing comment may follow the ';'
        if code.endswith(";"):
            stmt = "".join(buf).rstrip()
            out.append(stmt[: stmt.rfind(";")])               # drop the ';' and anything after it
            buf = []
    return out


def main():
    con = hcconfig.exasol()
    for st in statements(ROOT / "sql" / "40_governed_views.sql"):
        try:
            con.execute(st)
        except pyexasol.ExaQueryError as e:
            if not (st.startswith("CREATE ROLE") and "conflicts" in e.message):
                sys.exit(f"failed: {st[:80]}\n{e.message}")
    pw = dict(l.strip().split("=", 1) for l in open(ENV) if "=" in l) if ENV.exists() else {}
    existing = {r[0] for r in con.execute("SELECT USER_NAME FROM EXA_DBA_USERS").fetchall()}
    for u in USERS:
        if u not in pw:
            pw[u] = "Hc" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")
        if u in existing:
            con.execute(f'ALTER USER {u} IDENTIFIED BY "{pw[u]}"')
        else:
            con.execute(f'CREATE USER {u} IDENTIFIED BY "{pw[u]}"')
        con.execute(f"GRANT CREATE SESSION TO {u}")
        con.execute(f"GRANT HOSP_AGENT_READER TO {u}")
    ENV.parent.mkdir(exist_ok=True)
    old = os.umask(0o077)
    ENV.write_text("".join(f"{u}={p}\n" for u, p in pw.items()))
    os.umask(old)
    print(f"governed views + users {', '.join(USERS)} ready (passwords in {ENV})")


if __name__ == "__main__":
    main()
