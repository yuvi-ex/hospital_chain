"""Snapshot the live dash-server console into ONE self-contained HTML file for reviewers.
    .venv/bin/python tools/export_static.py <out.html>
Captures every tab in its 'after the demo' state (all six questions answered, a DICOM rendered, the agent run, the trace),
inlines every image as a data URI and strips signed S3 links (they carry the reader key id and expire in 15 min)."""
import base64, re, sys, time, urllib.request
from datetime import date
from playwright.sync_api import sync_playwright

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig  # noqa: E402

URL = f"http://127.0.0.1:{hcconfig.DASH_PORT}/apps/{hcconfig.APP}/"
OUT = sys.argv[1]
GRAB = "() => document.querySelector('.tab-content').innerHTML"

def settle(pg, sel, t=150000):
    pg.wait_for_selector(sel, timeout=t); time.sleep(3)

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1200})
    pg.goto(URL); settle(pg, ".hw-pic", 120000)
    css = pg.evaluate("() => [...document.querySelectorAll('style')].map(s => s.textContent).join('\\n')")
    head = pg.evaluate("() => { const p = document.querySelector('.page'); const out = [];"
                       " for (const c of p.children) { if (c.querySelector && c.querySelector('#tabs')) break; out.push(c.outerHTML); } return out.join(''); }")
    panes = {"over": pg.evaluate(GRAB)}
    pg.get_by_text("2 · Live demo", exact=True).click(); time.sleep(1)
    demo = []
    for n in range(6):
        btn = pg.locator(".qbtns button").nth(n); label = btn.inner_text().split("·", 1)[-1].strip()
        btn.click()
        pg.wait_for_function("""l => { const a = document.getElementById('answer'), q = a && a.querySelector('.q');
            return q && q.textContent.trim().slice(0, 18) === l.slice(0, 18) && !a.hasAttribute('data-dash-is-loading'); }""", arg=label, timeout=150000)
        time.sleep(3)
        if n == 2:  # scans: render one DICOM live so reviewers see the step timings
            pg.locator("text=Render it from the DICOM file now").nth(0).click()
            settle(pg, "text=Rendered here from the original DICOM file", 90000)
        demo.append(pg.evaluate(GRAB)); print("demo", n + 1, flush=True)
    pg.get_by_text("3 · Who is asking", exact=True).click(); time.sleep(1)
    pg.click("#ag-ask"); settle(pg, "text=What the agent did")
    pg.click("#ag-bypass"); settle(pg, ".ag-no, .cached")
    pg.click("#ag-audit"); settle(pg, ".ag-aud", 60000)
    panes["agent"] = pg.evaluate(GRAB); print("agent", flush=True)
    pg.get_by_text("4 · How it works", exact=True).click(); settle(pg, ".hw3", 60000)
    pg.click("#flow-trace"); settle(pg, ".fw-tr.tot", 60000)
    panes["flow"] = pg.evaluate(GRAB); print("flow", flush=True)
    b.close()

def inline(h):
    def img(m):
        src = m.group(2)
        if src.startswith("data:"):
            return m.group(0)
        with urllib.request.urlopen(src.replace("&amp;", "&"), timeout=60) as r:
            mime = r.headers.get_content_type()
            return f'{m.group(1)}data:{mime};base64,{base64.b64encode(r.read()).decode()}"'
    h = re.sub(r'(<img[^>]*?src=")([^"]+)"', img, h)
    # signed links: drop the href, keep the label
    h = re.sub(r'href="[^"]*X-Amz-[^"]*"', 'title="Signed link (15 min) removed from this review copy"', h)
    assert "ETL-" not in h and 'class="cached"' not in h, "a pane shows a fallback/error, not live data: run setup/preflight.sh first"
    assert "X-Amz-Signature" not in h and "AKIA" not in h, "signed URL left in the snapshot"
    return h

imports = re.findall(r"@import url\([^)]*\)[^;]*;", css)
css = "\n".join(imports) + "\n" + re.sub(r"@import url\([^)]*\)[^;]*;", "", css)
panes = {k: inline(v) for k, v in panes.items()}
demo = [inline(d) for d in demo]
head = inline(head)
for d in demo:  # mark the question buttons so only they stay clickable
    pass
tabs = [("over", "1 · Overview"), ("demo", "2 · Live demo"), ("agent", "3 · Who is asking"), ("flow", "4 · How it works")]
bar = "".join(f'<div class="tab{" tab--selected" if k == "over" else ""}" data-t="{k}"><span>{l}</span></div>' for k, l in tabs)
body = (f'<div class="pane" id="p-over">{panes["over"]}</div>'
        f'<div class="pane" id="p-demo" hidden>' + "".join(f'<div class="snap-q" id="q{i}"{"" if i == 0 else " hidden"}>{d}</div>' for i, d in enumerate(demo)) + '</div>'
        f'<div class="pane" id="p-agent" hidden>{panes["agent"]}</div><div class="pane" id="p-flow" hidden>{panes["flow"]}</div>')
SNAP_CSS = """
:root { color-scheme: light; }
body { background:#F4F7FB; margin:0; }
.page { padding-left:max(16px, env(safe-area-inset-left, 0px)) !important; padding-right:max(16px, env(safe-area-inset-right, 0px)) !important; overflow-x:hidden; }
.snap-note { margin:0 0 .8rem; border-radius:12px; background:#FFF8E6; border:1px solid #F1D48A; color:#5C4300; padding:.55rem .85rem; font-size:.86rem; line-height:1.45; }
.snap-note b { font-weight:800; }
.tabbar { display:flex !important; flex-direction:row !important; flex-wrap:wrap; gap:0 1.4rem; } .tabbar .tab { cursor:pointer; width:auto !important; flex:0 0 auto !important; display:block !important; }
.pane button, .pane input, .pane textarea, .pane select { pointer-events:none; }
.pane .qbtns button { pointer-events:auto; cursor:pointer; }
"""
JS = """
<script>
(function () {
  const tabs = document.querySelectorAll('.tabbar .tab');
  function show(k) {
    tabs.forEach(t => t.classList.toggle('tab--selected', t.dataset.t === k));
    document.querySelectorAll('.pane').forEach(p => { p.hidden = p.id !== 'p-' + k; });
    try { history.replaceState(null, '', '#' + k); } catch (e) {}
  }
  tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.t)));
  document.querySelectorAll('#p-demo .snap-q').forEach(q => {
    q.querySelectorAll('.qbtns button').forEach((btn, i) => btn.addEventListener('click', () => {
      document.querySelectorAll('#p-demo .snap-q').forEach((o, j) => { o.hidden = j !== i; });
    }));
  });
  const h = (location.hash || '').slice(1);
  if (['over', 'demo', 'agent', 'flow'].includes(h)) show(h);
})();
</script>"""
note = (f'<div class="snap-note"><b>Review copy.</b> A snapshot of the live demo, captured {date.today():%d %b %Y} with real query results. '
        'The tabs and the six questions work; other buttons show the result they produced. Patients are synthetic; images are de-identified '
        'studies from The Cancer Imaging Archive (CC BY 4.0).</div>')
html = (f'<title>Patient Federation Demo</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
        f'<style>{css}\n{SNAP_CSS}</style>\n<div class="page">{note}{head}'
        f'<div class="tab-parent tabs-wrap"><div class="tab-container tabbar">{bar}</div><div class="tab-content">{body}</div></div></div>{JS}')
open(OUT, "w").write(html)
print(f"wrote {OUT}: {len(html) / 1e6:.1f} MB")
