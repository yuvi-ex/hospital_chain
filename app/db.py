"""The Exasol connection (Exasol Personal on this laptop), timed queries, and a cached fallback.

Every successful result is written to cache/<key>.json. If a live source fails on
stage, the page shows the last good result and labels it as cached, never silently.
One connection per database: Exasol Personal has a 20-session cap shared with the
other demos on this laptop.
"""
import json
import re
import time
import tomllib
from pathlib import Path

import pyexasol
import streamlit as st

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def _laptop():
    c = tomllib.load(open(Path.home() / ".exapump" / "config.toml", "rb"))[__import__("hcconfig").EXAPUMP_PROFILE]
    return pyexasol.connect(dsn=f"{c['host']}:{c['port']}", user=c["user"], password=c["password"],
                            encryption=True, websocket_sslopt={"cert_reqs": 0}, fetch_dict=True)


_NUM = re.compile(r"^-?\d+(\.\d+)?$")


def _num(v):
    """pyexasol returns DECIMAL as str; turn numeric strings into numbers for display."""
    if isinstance(v, str) and _NUM.match(v):
        return float(v) if "." in v else int(v)
    return v


_FACTORY = {"laptop": _laptop}
_DOWN = {}          # which -> time of the last failed connect; skip retries for 30 s so the page never hangs
_BACKOFF = 30


def _check_down(which):
    if time.time() - _DOWN.get(which, 0) < _BACKOFF:
        raise ConnectionError(f"Exasol {which} is not reachable (retrying in a few seconds)")


@st.cache_resource(show_spinner=False)
def _conn(which: str):
    _check_down(which)
    try:
        con = _FACTORY[which]()
    except Exception:
        _DOWN[which] = time.time()
        raise
    con.execute("ALTER SESSION SET QUERY_TIMEOUT = 120")
    return con


def run(which: str, sql: str, key: str | None = None) -> dict:
    """Run sql on 'laptop' or 'cloud'. Returns {rows, cols, secs, live, error, at}."""
    t = time.time()
    try:
        try:
            stmt = _conn(which).execute(sql)
        except (pyexasol.ExaCommunicationError, pyexasol.ExaConnectionError):
            _conn.clear()                      # dropped socket: reconnect once
            _check_down(which)
            stmt = _conn(which).execute(sql)
        if stmt.result_type == "resultSet":
            rows, cols = [{k: _num(v) for k, v in r.items()} for r in stmt.fetchall()], list(stmt.column_names())
        else:  # DDL / CTAS: report the affected row count as a one-row result
            rows, cols = [{"ROWS_WRITTEN": stmt.rowcount()}], ["ROWS_WRITTEN"]
        res = {"rows": rows, "cols": cols, "secs": time.time() - t,
               "live": True, "error": None, "at": time.strftime("%H:%M:%S")}
        if key:
            CACHE.mkdir(exist_ok=True)
            (CACHE / f"{key}.json").write_text(json.dumps(res, default=str))
        return res
    except Exception as e:  # noqa: BLE001 - any failure falls back to the cached result
        msg = getattr(e, "message", str(e))
        f = CACHE / f"{key}.json" if key else None
        if f and f.exists():
            res = json.loads(f.read_text())
            res.update(live=False, error=msg[:300])
            return res
        return {"rows": [], "cols": [], "secs": time.time() - t, "live": False, "error": msg[:300], "at": None}


def ping(which: str) -> bool:
    try:
        _conn(which).execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        _conn.clear()
        return False
