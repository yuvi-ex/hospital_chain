#!/usr/bin/env python3
"""Refresh the two appendices of docs/tech-spec.html from the real files, so the document never drifts from the code.

    .venv/bin/python docs/build_appendix.py
Appendix A: every sql/*.sql file. Appendix B: every console query (dash/console.py QUERIES + EXPLAIN).
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "tech-spec.html"
sys.path.insert(0, str(ROOT / "dash"))
import console  # noqa: E402


def block(title, sql):
    return f'<h3><code>{html.escape(title)}</code></h3>\n<pre><code>{html.escape(sql.strip())}</code></pre>\n'


def replace(doc, tag, body):
    return re.sub(rf"<!--{tag}-START-->.*?<!--{tag}-END-->", lambda _: f"<!--{tag}-START-->\n{body}<!--{tag}-END-->", doc, flags=re.S)


doc = DOC.read_text()
doc = replace(doc, "APPX-SQL", "".join(block(f"sql/{p.name}", p.read_text()) for p in sorted((ROOT / "sql").glob("*.sql"))))
q = "".join(block(f"queries/business/{k}.sql", v) for k, v in console.QUERIES.items())
q += "".join(block(f"explain/{k}.sql", "EXPLAIN VIRTUAL " + v) for k, v in console.EXPLAIN.items())
doc = replace(doc, "APPX-Q", q)
DOC.write_text(doc)
print(f"appendices refreshed: {len(list((ROOT / 'sql').glob('*.sql')))} SQL files, {len(console.QUERIES) + len(console.EXPLAIN)} queries")
