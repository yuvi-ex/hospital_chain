"""Hospital-chain demo on dash-server: one patient, every branch.

Four tabs: the problem and the architecture (Overview), six live questions (Live demo), the same question through the
Exasol MCP server as two named people (Who is asking), and the flow with one question traced (How it works).
Every query runs through the dash-server Exasol profile (the kit's read-only user). The HTML builders come from the
Streamlit console in ../app, so both versions read the same.
"""
import base64
import json
import re
import time
from pathlib import Path

from dash import ALL, MATCH, Dash, Input, Output, State, ctx, dcc, html, no_update

import agent_tab as ag
import console as C
import flow
import how
import scans
import story
from dash_server_exasol import has_error, load_rows
from page_css import PAGE_CSS
from theme import CSS as THEME_CSS

HERE = Path(__file__).resolve().parent


def _css(s):
    return s.replace("<style>", "").replace("</style>", "")


APP_CSS = """
.rec { display:grid; grid-template-columns:7.2rem minmax(0,1fr); gap:.7rem; align-items:start; border-bottom:1px solid #EEF2F7; padding:.5rem 0; }
.rec:last-child { border-bottom:0; }
.rec .sys { font-size:.62rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; border-radius:8px; padding:.25rem .45rem; text-align:center; }
.sys.legacy { background:#FFF4E5; color:#9A4A00; } .sys.modern { background:#E2F4FF; color:#0076AD; } .sys.pacs { background:#EEF0FF; color:#3B3FB8; }
.rec .id { font-family:'JetBrains Mono',monospace; font-size:.82rem; color:var(--ink2); font-weight:700; }
.rec .as { font-size:.86rem; color:var(--muted); margin-top:.1rem; } .rec .as b { color:var(--ink2); font-family:'JetBrains Mono',monospace; font-weight:600; }
.rec .why { font-size:.78rem; color:var(--teal-ink); font-weight:700; margin-top:.15rem; }
.alert { border-radius:14px; border:1px solid #F3C2C8; border-left:6px solid #C8102E; background:#FFF7F8; padding:.7rem .9rem; margin:.5rem 0; }
.alert .h { font-weight:900; color:#C8102E; font-size:1.05rem; } .alert .d { font-size:.9rem; color:var(--ink2); margin-top:.2rem; line-height:1.45; }
.alert .src { font-size:.74rem; color:var(--muted); margin-top:.3rem; }
.vs2c { display:grid; grid-template-columns:1fr auto 1fr; gap:.6rem; align-items:stretch; margin:.4rem 0; }
.vs2c .c { border-radius:14px; border:1px solid var(--edge); padding:.6rem .8rem; background:#fff; }
.vs2c .c .k { font-size:.62rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); }
.vs2c .c .v { font-weight:800; font-size:.98rem; margin-top:.15rem; color:var(--ink2); } .vs2c .c .s { font-size:.78rem; color:var(--muted); margin-top:.15rem; }
.vs2c .c.bad { border-color:#F3C2C8; background:#FFF7F8; } .vs2c .c.bad .v { color:#C8102E; }
.vs2c .x { display:flex; align-items:center; font-weight:900; color:#C8102E; font-size:1.3rem; }
.quote { font-family:'JetBrains Mono',monospace; font-size:.74rem; color:#5B4A00; background:#FFFBEA; border:1px solid #F5E3A1; border-radius:10px; padding:.5rem .7rem; margin:.4rem 0; line-height:1.5; }
.sim { display:grid; grid-template-columns:minmax(0,1fr) 8rem 4.2rem; gap:.6rem; align-items:center; border-bottom:1px solid #EEF2F7; padding:.42rem 0; }
.sim:last-child { border-bottom:0; } .sim .nm { font-weight:800; font-size:.9rem; } .sim .mt { font-size:.78rem; color:var(--muted); line-height:1.35; }
.sim .ab { font-weight:800; color:var(--teal-ink); font-size:.86rem; text-align:right; } .sim .ls { text-align:right; font-variant-numeric:tabular-nums; font-weight:800; }
.sim .ls span { display:block; font-size:.68rem; color:var(--faint); font-weight:600; }
.tag { display:inline-block; font-size:.6rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; border-radius:999px; padding:.05rem .45rem; margin-left:.3rem; }
.tag.r { background:#FDE7EA; color:#C8102E; } .tag.g { background:#E3F5F1; color:#12796A; } .tag.b { background:#E2F4FF; color:#0076AD; }
.rb { display:grid; grid-template-columns:9rem 1fr 5rem; gap:.7rem; align-items:center; margin:.45rem 0; }
.rb .l { font-weight:800; font-size:.92rem; } .rb .l span { display:block; font-weight:600; font-size:.72rem; color:var(--faint); }
.rb .t { height:28px; border-radius:8px; background:#F1F4F9; display:flex; overflow:hidden; }
.rb .t .v1 { background:#1FA08B; } .rb .t .v2 { background:repeating-linear-gradient(45deg,#C8102E 0 6px,#E0505F 6px 12px); }
.rb .n { text-align:right; font-weight:900; font-variant-numeric:tabular-nums; }
.leg { display:flex; gap:1rem; font-size:.78rem; color:var(--muted); margin:.2rem 0 .3rem; } .leg i { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:.35rem; vertical-align:-1px; }
"""

# Dash wiring: page shell, tabs, buttons, details, code. Everything else is the Streamlit console's CSS.
DASH_CSS = """
html, body { margin:0; }
body { font-family:"Figtree",sans-serif; color:var(--ink);
  background: radial-gradient(circle at top left, rgba(226,244,255,0.95), transparent 30%),
              radial-gradient(circle at top right, rgba(227,245,241,0.85), transparent 26%),
              linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 55%, #ffffff 100%); background-attachment:fixed; min-height:100vh; }
.page { padding:1.4rem 2.2rem 3rem; max-width:1800px; margin:0 auto; }
.md > p:empty { display:none; } .md p { margin:0; }
.tabbar { border-bottom:1px solid var(--line) !important; margin-bottom:.6rem; }
.tabbar .tab { background:transparent !important; border:0 !important; border-bottom:3px solid transparent !important; font-weight:600; font-size:.95rem;
  color:var(--muted) !important; padding:.55rem 0 !important; margin-right:1.6rem; width:auto !important; flex:0 0 auto !important; }
.tabbar .tab--selected { color:var(--bad) !important; border-bottom-color:var(--bad) !important; }
.two { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:2rem; align-items:start; }
.two.even { grid-template-columns:minmax(0,1fr) minmax(0,1.1fr); }
.btn { font-family:"Figtree",sans-serif; font-weight:600; font-size:.92rem; border-radius:12px; border:1px solid rgba(31,160,139,.35);
  background:linear-gradient(135deg,#081226 0%,#10203F 100%); color:#fff; padding:.6rem 1rem; cursor:pointer; text-align:left; }
.btn:hover { filter:brightness(1.18); } .btn.wide { width:100%; }
.btn.ghost { background:#fff; color:var(--ink2); border:1px solid var(--edge); }
.btn.on { background:linear-gradient(135deg,#12796A 0%,#1FA08B 100%); border-color:#1FA08B; }
.btn.sm { font-size:.8rem; padding:.4rem .75rem; border-radius:10px; }
.qbtns { display:grid; gap:.45rem; margin-bottom:.8rem; } .qbtns .btn { min-height:2.8rem; font-size:.95rem; padding-left:1rem; }
.row2 { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; margin:.4rem 0 .8rem; }
.seg { display:flex; gap:.5rem; flex-wrap:wrap; margin:.3rem 0 .7rem; }
.simbox { display:grid; grid-template-columns:1fr auto; gap:.5rem; margin:-.2rem 0 .8rem; }
.simbox label { grid-column:1/-1; font-size:.8rem; color:var(--muted); }
.inp { font-family:"Figtree",sans-serif; font-size:.92rem; border-radius:12px; border:1px solid var(--edge); padding:.55rem .8rem; background:#fff; }
details.eng { border-radius:14px; border:1px solid var(--edge); background:#fff; margin:.8rem 0; padding:.2rem .9rem; }
details.eng > summary { cursor:pointer; font-weight:700; font-size:.9rem; color:var(--ink2); padding:.55rem 0; }
.cap2 { font-size:.78rem; color:var(--faint); margin:.6rem 0 .25rem; font-weight:700; }
pre.sql { font-family:"JetBrains Mono",monospace; font-size:.74rem; line-height:1.5; background:#0B1730; color:#DCE6F5; border-radius:12px;
  padding:.7rem .9rem; white-space:pre-wrap; word-break:break-word; margin:.2rem 0 .6rem; max-height:28rem; overflow:auto; }
.ok-note { border-radius:12px; background:#E3F5F1; border:1px solid #CDEBE4; color:#12796A; padding:.5rem .8rem; font-size:.86rem; margin:.4rem 0; }
/* the PACS: one row per study, image left, how it got here right */
.scan2 { display:grid; grid-template-columns:minmax(0,15rem) minmax(0,1fr); gap:1rem; border-radius:16px; border:1px solid var(--edge);
  background:#fff; padding:.8rem; margin:.6rem 0; }
.scan2 .imgs { display:grid; gap:.4rem; align-content:start; }
.scan2 .imgs img { display:block; width:100%; height:15rem; object-fit:contain; background:#000; border-radius:10px; }
.scan2 .imgs .il { font-size:.66rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--faint); text-align:center; }
.scan2 .t { font-weight:800; font-size:.98rem; color:var(--ink2); } .scan2 .m { font-size:.82rem; color:var(--muted); margin:.1rem 0 .45rem; }
.scan2 .m code { font-size:.76rem; }
.how { counter-reset:h; margin:.2rem 0 .5rem; padding:0; list-style:none; }
.how li { counter-increment:h; display:grid; grid-template-columns:1.5rem minmax(0,1fr) auto; gap:.5rem; align-items:start; font-size:.82rem;
  line-height:1.4; padding:.28rem 0; border-top:1px dashed #E5EAF1; color:var(--ink2); }
.how li:first-child { border-top:0; }
.how li::before { content:counter(h); width:1.35rem; height:1.35rem; border-radius:50%; background:#3B3FB8; color:#fff; font-weight:800; font-size:.7rem;
  display:flex; align-items:center; justify-content:center; }
.how li.ex::before { background:#12796A; } .how li.br::before { background:#0076AD; }
.how li .s { font-size:.72rem; color:var(--faint); white-space:nowrap; font-variant-numeric:tabular-nums; }
.how li code { font-size:.72rem; }
.s3box { border-radius:12px; background:#F5F6FF; border:1px solid #C9CCF7; padding:.5rem .7rem; margin:.3rem 0 .5rem; }
.s3box .k { font-size:.62rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:#3B3FB8; }
.s3box .u { font-family:'JetBrains Mono',monospace; font-size:.72rem; color:var(--ink2); word-break:break-all; margin:.15rem 0 .35rem; user-select:all; }
.s3box a { font-size:.78rem; font-weight:800; color:#0076AD; text-decoration:none; margin-right:1rem; }
.rtags { display:flex; flex-wrap:wrap; gap:.3rem; margin:.4rem 0; }
.rtags span { font-size:.7rem; background:#F1F4F9; border-radius:6px; padding:.1rem .4rem; color:var(--ink2); } .rtags b { color:var(--faint); font-weight:700; }
@media (max-width:1100px) { .two, .two.even { grid-template-columns:1fr; } .scan2 { grid-template-columns:1fr; } .page { padding:1rem; } }
"""

STYLE = (_css(THEME_CSS) + _css(PAGE_CSS) + APP_CSS + _css(ag.CSS) + _css(flow.CSS) + story.CSS + how.CSS + DASH_CSS)
# All CSS inline: dash-server loads app.py under a synthetic module name, and an assets/ stylesheet is easy to lose.
INDEX = ("<!DOCTYPE html><html lang=\"en\"><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}<style>" + STYLE
         + "</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>")


_VOID = re.compile(r"<(br|hr|img|wbr)(\s[^<>]*?)?(?<!/)>")


def H(fragment, **kw):
    """Raw HTML (the console's builders) as one Markdown block: no blank lines, no indentation, so nothing becomes markdown."""
    text = "\n".join(l.strip() for l in str(fragment).splitlines() if l.strip())
    # dcc.Markdown renders a whole block as NOTHING (no error anywhere) if it holds an unclosed void tag such as <br>
    text = _VOID.sub(r"<\1\2/>", text)
    text = C.generic(text)
    return dcc.Markdown(text, dangerously_allow_html=True, className="md", **kw)


def _all_live(v):
    """True unless v holds a run() result (dict with "live") that came from the cache instead of the source."""
    if isinstance(v, dict):
        return v.get("live", True) is not False and all(_all_live(x) for x in v.values() if isinstance(x, (dict, tuple, list)))
    if isinstance(v, (tuple, list)):
        return all(_all_live(x) for x in v if isinstance(x, (dict, tuple, list)))
    return True


def _memo(ttl):
    store = {}

    def deco(fn):
        def wrap(*a):
            hit = store.get(a)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
            val = fn(*a)
            if _all_live(val):              # a failed source is retried on the next request, never pinned for the TTL
                store[a] = (time.time(), val)
            return val
        return wrap
    return deco


@_memo(20)
def health():
    out = {k: C.run(f"health_{k}", cache=False)["live"] for k in C.HEALTH if k != "s3"}
    out["s3"] = _health_s3()["live"]
    return out


@_memo(600)
def _health_s3():
    """S3 bills per request: the archive is probed at most every 10 minutes per console (a failure is retried at once)."""
    return C.run("health_s3", cache=False)


@_memo(600)
def overview_data():
    return {k: C.run(k) for k in ("who", "allergy", "chain", "readm_fast", "mpi_total", "inbed")}


@_memo(600)
def flow_counts():
    return C.run("flow_counts"), C.run("scans_all")


def _logo():
    b64 = base64.b64encode((HERE / "assets" / "exasol_logo_dark.svg").read_bytes()).decode()
    return (f'<img src="data:image/svg+xml;base64,{b64}" alt="Exasol" width="104" height="26" '
            f'style="height:26px;width:auto;max-width:104px;display:block;"/>')


def hero(h):
    # state in words and a symbol, not by colour alone
    pill = lambda ok, t: f'<span class="hs-pill{"" if ok else " down"}">{"&#10003;" if ok else "&#10005;"} {t}{"" if ok else " · down"}</span>'  # noqa: E731
    return (f'<div class="hero-slim"><div class="hs-t">Every branch\'s record of a patient, <em>in one query</em>'
            f'<span>An old hospital information system, a modern electronic health record and an imaging archive, federated by one Exasol endpoint, each system queried where it is.</span></div>'
            f'<div class="hs-m">{pill(h["exa"], "Exasol")}{pill(h["pg"], "Legacy HIS")}{pill(h["mongo"], "Modern EHR")}{pill(h["s3"], "PACS on S3")}</div></div>')


# ------------------------------------------------------------------ static blocks
DATA_MAP = [("Branch A", "Legacy HIS", "Postgres", "PAT_MSTR 874 · VISIT_HDR 3,365", "<b>Hospital information system</b>: registration, admissions, pharmacy, labs. 2009-era schema: dates as text, surnames as initials, allergies as free text"),
            ("Branch B", "Modern EHR", "MongoDB", "patients 735 · encounters 2,605", "<b>Electronic health record</b>: the clinical record. FHIR-style documents with allergies, medications and vitals nested inside"),
            ("Branch C", "Both", "migrating", "HIS until Mar 2024, EHR since", "the same patients registered twice, once in each system"),
            ("Imaging", "PACS", "Amazon S3", "168 DICOM studies · X-ray, CT, MRI", "<b>Picture archiving and communication system</b>: where the scanners store images (DICOM files); a header index sits beside them"),
            ("Exasol", "Patient index", "+ note vectors", "1,609 records &rarr; 1,224 people", "deterministic matching rules in SQL; 3,976 notes embedded")]
DATA_MAP_HTML = ('<div class="qk" style="margin-top:.2rem">What data lives where</div><div class="dmap">' + "".join(
    f'<div class="dm{" exa" if k == "Exasol" else ""}"><div class="dk">{k}</div><div class="ds">{sy} <span>{role}</span></div>'
    f'<div class="dt">{tables}</div><div class="dd">{d}</div></div>' for k, sy, role, tables, d in DATA_MAP) + "</div>")

FAIL3 = '''<div class="ov-band"><div class="ov-k">What has been tried</div><div class="ov-h">Three ways around it, and why they break</div></div>
<div class="fail3">
<div class="f3"><div class="f3-k">Breaks down</div><div class="f3-t">Migrate every branch first</div><div class="f3-d">Years before the first answer</div></div>
<div class="f3"><div class="f3-k">Breaks down</div><div class="f3-t">Phone and fax between branches</div><div class="f3-d">The record arrives after the prescription</div></div>
<div class="f3"><div class="f3-k">Breaks down</div><div class="f3-t">Copy everything to a lake</div><div class="f3-d">One more pipeline, PHI in one more place</div></div>
<div class="f3-ar">&rarr;</div>
<div class="f3 good"><div class="f3-k">With Exasol</div><div class="f3-t">One patient, live</div><div class="f3-d">Federate &middot; resolve identity &middot; certify meaning</div></div></div>'''

GLOSSARY = '''<div class="dmap" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-top:.8rem">
<div class="dm"><div class="dk">HIS</div><div class="ds">Hospital information system <span>the older system</span></div>
<div class="dd">Runs the hospital: registration, admissions and discharges, billing, pharmacy orders, lab results. Here: Branch A, on Postgres.</div></div>
<div class="dm"><div class="dk">EHR</div><div class="ds">Electronic health record <span>the newer system</span></div>
<div class="dd">The clinical record of the patient: problems, allergies, medications, vitals, notes. Here: Branch B, on MongoDB.</div></div>
<div class="dm"><div class="dk">PACS</div><div class="ds">Picture archiving and communication system</div>
<div class="dd">Where the X-ray, CT and MRI scanners store images, as DICOM files with a header (patient ID, date, body part). Here: Amazon S3.</div></div></div>'''

LAYERS = '''<div class="ov-band"><div class="ov-k">Reading the diagram</div><div class="ov-h">Identity first, then meaning, then execution</div></div>
<div class="layers">
<div class="ly"><div class="ly-n">People</div><div class="ly-t">Clinicians, analysts and their AI agents: one endpoint, any tool</div></div>
<div class="ly dark"><div class="ly-n">Semantic views</div><div class="ly-t">One definition of a patient, a readmission and a drug conflict for every branch</div></div>
<div class="ly exa"><div class="ly-n">Patient index</div><div class="ly-t">Which records are the same person, with the reason for every link</div></div>
<div class="ly exa"><div class="ly-n">Virtual schemas</div><div class="ly-t">Each branch system queried where it is, read-only</div></div>
<div class="ly"><div class="ly-n">Branch systems</div><div class="ly-t">Stay where they are, owned by their teams, migrated when it suits</div></div></div>'''

PATH5 = '''<div class="ov-band"><div class="ov-k">The adoption path</div><div class="ov-h">Federate first. Accelerate what earns it.</div></div>
<div class="path5">
<div class="p5 done"><div class="p5-n">1</div><div class="p5-t">Attach</div><div class="p5-d">each branch system, read-only</div><div class="p5-s">in this demo</div></div>
<div class="p5 done"><div class="p5-n">2</div><div class="p5-t">Resolve</div><div class="p5-d">one patient, every record</div><div class="p5-s">in this demo</div></div>
<div class="p5 sv"><div class="p5-n">3</div><div class="p5-t">Certify</div><div class="p5-d">definitions, access, masking</div><div class="p5-s">semantic views</div></div>
<div class="p5 done"><div class="p5-n">4</div><div class="p5-t">Accelerate</div><div class="p5-d">copy the hot paths</div><div class="p5-s">in this demo</div></div>
<div class="p5"><div class="p5-n">5</div><div class="p5-t">Agent-enable</div><div class="p5-d">MCP, per-person rights</div><div class="p5-s">tab 3</div></div></div>
<div class="footnote">Data: patients, encounters and notes are synthetic (generated, seeded). Images are real, de-identified studies from
The Cancer Imaging Archive (COVID-19-AR and UPENN-GBM, CC BY 4.0), relabelled to synthetic patients. No real hospital systems are involved.</div>'''


def overview():
    d = overview_data()
    # One picture and three numbers. The architecture, the patient index and the readmission detail live in tabs 2 and 4.
    return html.Div([H(story.problem(d["who"], d["allergy"], d["chain"], d["readm_fast"], d["mpi_total"], d["inbed"])),
                     H('<div class="footnote" style="margin-top:1rem">Synthetic patients; real de-identified images from The Cancer Imaging Archive '
                       '(CC BY 4.0). No real hospital systems are involved.</div>')])


def _overview_full():
    """The longer overview, kept for reference (not shown)."""
    d = overview_data()
    parts = [FAIL3, GLOSSARY]
    top = html.Div([H(p) for p in parts])
    mid = html.Div(className="two even", children=[
        html.Div([H('<div class="ov-band"><div class="ov-k">How it connects</div><div class="ov-h">One path for every question</div></div>'),
                  H(C.diagram(None))]),
        html.Div([H(LAYERS)])])
    tot = (d["mpi_total"]["rows"] or [{}])[0]
    qf = C.CACHE / "mpi_quality.json"
    qual = json.loads(qf.read_text()) if qf.exists() else {}
    tail = ""
    if tot:
        tail += f'''<div class="ov-band"><div class="ov-k">Why a patient index</div>
<div class="ov-h">{int(tot["RECORDS"]):,} records, {int(tot["PEOPLE"]):,} people</div>
<div class="ov-s">The same person registered at several branches, with initials for surnames, day and month swapped, landlines
instead of mobiles. Deterministic rules in SQL link them; borderline pairs go to a person, never to a guess.</div></div>
<div class="tok"><div class="tk2"><div class="v">{int(tot["RECORDS"]):,}</div><div class="k">patient records across the legacy HIS and the modern EHR</div></div>
<div class="tka">&rarr;</div><div class="tk2 good"><div class="v">{int(tot["PEOPLE"]):,}</div><div class="k">people, one UNIFIED_ID each</div></div>
<div class="tka">&middot;</div><div class="tk2 navy"><div class="v">{qual.get("precision_pct", "–")}% &middot; {qual.get("recall_pct", "–")}%</div>
<div class="k">links correct &middot; true links found (measured against the generator's ground truth; {int(tot["REVIEW"]):,} pairs queued for review)</div></div></div>'''
    rd = d["readm_fast"]["rows"]
    if rd:
        allr = sum(int(r["READMISSIONS"]) for r in rd)
        vis = allr - sum(int(r["HIDDEN"]) for r in rd)
        tail += f'''<div class="ov-band"><div class="ov-k">Why a certified definition</div>
<div class="ov-h">Wrong but plausible is worse than an error</div>
<div class="ov-s">"30-day readmissions across the chain", measured on this demo's data, two ways.</div></div>
<div class="fan">
<div class="fn-row"><div class="fn-l">Each branch system counts its own<span>the SQL runs fine</span></div>
<div class="fn-tr"><div class="fn-f bad" style="width:{100 * vis / allr:.1f}%"><span>{vis}</span></div></div></div>
<div class="fn-row"><div class="fn-l">Certified definition<span>same person, any branch</span></div>
<div class="fn-tr"><div class="fn-f good" style="width:100%"><span>{allr}</span></div></div></div>
<div class="fn-foot"><span class="fn-x">{100 * (allr - vis) / allr:.0f}% under-counted</span>
{allr - vis} readmissions cross a branch or a system, so no single system can see them.
<b>HOSP_GOV.READMISSIONS_30D carries the one definition every tool uses.</b></div></div>'''
    return html.Div([top, mid, H(tail), H(PATH5)])


# ------------------------------------------------------------------ the PACS cards
def scan_cards(out):
    res = out["main"]
    cards = []
    for i, r in enumerate(res["rows"]):
        ln = scans.links(r["S3_KEY"])
        thumb, dcm = scans.signed(r["THUMB_KEY"]), scans.signed(r["S3_KEY"])
        sop = r["THUMB_KEY"].split("/")[-1]
        how = (f'<ol class="how">'
               f'<li class="ex"><div>Exasol read the PACS header index in place: <code>index/dicom_index.csv</code> on S3, through '
               f'<code>CONNECTION HOSP_S3</code> (read-only)</div><div class="s">{res["secs"]:.1f} s</div></li>'
               f'<li class="ex"><div>The patient index matched the DICOM PatientID tag <code>{C.esc(r["PACS_PATIENT_ID"])}</code> to her</div><div class="s">same query</div></li>'
               f'<li class="ex"><div>Exasol returned this file\'s S3 key and its size ({float(r["FILE_BYTES"] or 0) / 1024:,.0f} KB). Not one pixel.</div><div class="s"></div></li>'
               f'<li><div>This console signed a GET for that one key: SigV4, {scans.REGION}, valid 15 minutes, by the read-only IAM user <code>hc-s3-reader</code></div><div class="s"></div></li>'
               f'<li class="br"><div>Your browser downloaded the preview straight from S3: <code>thumbs/{C.esc(sop[:18])}&hellip;png</code>, '
               f'made from this DICOM file when it was archived</div><div class="s"></div></li></ol>')
        s3 = (f'<div class="s3box"><div class="k">This file on Amazon S3</div><div class="u">{C.esc(ln["uri"])}</div>'
              f'<a href="{ln["console"]}" target="_blank">Open in the AWS console &rarr;</a>'
              f'<a href="{dcm}" target="_blank">Download the DICOM (signed, 15 min) &rarr;</a>'
              f'<a href="{thumb}" target="_blank">Preview PNG &rarr;</a></div>')
        cards.append(html.Div(className="scan2", children=[
            html.Div(className="imgs", children=[html.Img(src=thumb, alt=r["STUDY_DESCRIPTION"]), html.Div("preview, from S3", className="il"),
                                                 html.Div(id={"type": "rimg", "i": i})]),
            html.Div([
                H(f'<div class="t">{C.esc(r["STUDY_DATE"])} &middot; {C.esc(r["STUDY_DESCRIPTION"])}</div>'
                  f'<div class="m">{C.esc(r["INSTITUTION"])} &middot; {C.esc(r["MODALITY"])} &middot; accession <code>{C.esc(r["ACCESSION_NUMBER"])}</code> '
                  f'&middot; name in the file <code>{C.esc(r["NAME_IN_DICOM"])}</code></div>'),
                H('<div class="cap2" style="margin-top:.1rem">How this image reached your screen</div>' + how),
                H(s3),
                html.Button("Render it from the DICOM file now, step by step", id={"type": "render", "i": i}, className="btn sm"),
                dcc.Loading(html.Div(id={"type": "rout", "i": i}), type="dot"),
            ])]))
    return cards


def render_steps(r):
    if r.get("error") and not r.get("steps"):
        return H(f'<div class="cached">Could not render: {C.esc(r["error"])}</div>')
    rows = "".join(f'<li class="{"br" if "Download" in s["name"] else ""}"><div><b>{C.esc(s["name"])}</b> &middot; {C.esc(s["detail"])}</div>'
                   f'<div class="s">{s["secs"]:.2f} s</div></li>' for s in r["steps"])
    tot = sum(s["secs"] for s in r["steps"])
    tags = "".join(f'<span><b>{k}</b> {C.esc(v)}</span>' for k, v in (r.get("tags") or {}).items())
    err = f'<div class="cached">Stopped: {C.esc(r["error"])}</div>' if r.get("error") else ""
    return H(f'<div class="cap2">Rendered here from the original DICOM file, {tot:.2f} s in all</div><ol class="how">{rows}</ol>'
             f'<div class="cap2">The DICOM header, as read from the file</div><div class="rtags">{tags}</div>{err}')


def engineers(k, out):
    sql = C.question_sql(k, out)
    kids = [html.Div("The SQL you write in Exasol", className="cap2"), html.Pre(sql.strip()[:6000], className="sql")]
    if k in ("who", "allergy", "chain"):
        kids += [html.Div("The patient index behind UNIFIED_ID: deterministic rules in SQL (sql/20_mpi.sql)", className="cap2"),
                 html.Pre(C.mpi_rules(), className="sql")]
    if k == "allergy":
        kids += [html.Div("The 2019 note, read live from the legacy HIS", className="cap2"), html.Pre(C.Q_ALLERGY_NOTE, className="sql")]
    if k == "scans":
        kids += [html.Div("S3 received: one GET for index/dicom_index.csv, signed with the read-only key. The view behind it:", className="cap2"),
                 html.Pre(C.imaging_view(), className="sql")]
    if k == "readmit":
        kids += [html.Div("The same question on the copy inside Exasol", className="cap2"), html.Pre(C.Q_READM_FAST, className="sql"),
                 html.Div("The copy is built once with this statement (sql/50_accelerate.sql, run at set-up as admin; this console is read-only):", className="cap2"),
                 html.Pre(C.Q_ACCEL, className="sql")]
    if k in C.EXPLAIN:
        kids += [html.Button("Show what Postgres received (EXPLAIN VIRTUAL)", id={"type": "explain", "k": k}, className="btn sm ghost"),
                 dcc.Loading(html.Div(id={"type": "explain-out", "k": k}), type="dot")]
    return html.Details(className="eng", children=[html.Summary("For engineers: the SQL, and what each source received")] + kids)


# ------------------------------------------------------------------ layout
def demo_tab():
    return html.Div([
        H(DATA_MAP_HTML),
        html.Div(className="two", style={"marginTop": "1rem"}, children=[
            html.Div([html.Div(id="dgm", children=H(C.diagram(None))), html.Div(id="legend", children=H(C.legend(None)))]),
            html.Div([
                H('<div class="qk">Ask a question</div>'),
                html.Div(className="qbtns", children=[
                    html.Button(C.generic(f'{q["n"]}  ·  {q["ask"]}'), id={"type": "q", "k": k}, className="btn wide", n_clicks=0)
                    for k, q in C.QUESTIONS.items()]),
                html.Div(id="sim-box", className="simbox", style={"display": "none"}, children=[
                    html.Label("Or describe a case in your own words (leave empty to use her note from today)", htmlFor="sim-text"),
                    dcc.Input(id="sim-text", type="text", className="inp", debounce=True,
                              placeholder="elderly diabetic, fever and cough, crackles at the right base"),
                    html.Button("Search by meaning", id="sim-go", className="btn", n_clicks=0)]),
                dcc.Loading(html.Div(id="answer", children=H(
                    '<div class="ans"><div class="q">Pick a question</div><div class="hint">Mrs. Meenakshi Sundaram, 68, diabetic, was treated in '
                    'Branch A in 2019. Today she is admitted in Branch B with fever and breathlessness, and a doctor has drafted her first '
                    'prescription. Each question is answered live; the diagram lights up the systems it touches.</div></div>')), type="dot"),
            ])])])


def agent_tab():
    return html.Div([
        H('<div class="sec-h"><div class="k">Agents ask the questions now</div>'
          '<div class="t" style="font-weight:800;font-size:1.35rem">Whose identity reaches the data? Which definition does the query use? Can the answer be replayed?</div></div>'),
        html.Div("Who is asking?", className="cap2"),
        html.Div(className="seg", children=[
            html.Button(C.generic(f"{p[0]} ({p[1]})"), id={"type": "who", "u": u}, n_clicks=0, className="btn sm" + (" on" if i == 0 else " ghost"))
            for i, (u, p) in enumerate(ag.PEOPLE.items())]),
        html.Div(id="ag-head"),
        html.Div(className="row2", children=[
            html.Button("Ask through the Exasol MCP server", id="ag-ask", className="btn wide on", n_clicks=0),
            html.Button("Now try to read the raw identities", id="ag-bypass", className="btn wide", n_clicks=0)]),
        dcc.Loading(html.Div(id="ag-out"), type="dot"),
        html.Div(id="ag-cmp"),
        html.Div(id="ag-no"),
        H('<div class="qk" style="margin-top:1rem">Every call is on record</div>'),
        html.Button("Show the audit log", id="ag-audit", className="btn sm", n_clicks=0),
        dcc.Loading(html.Div(id="ag-aud"), type="dot"),
        H('<div class="footnote">Real Exasol MCP server, real database users, row filter and masking in the engine. The SQL is the one an AI client writes '
          'after reading the view definitions (fixed here; in Claude Desktop the model writes it live). Synthetic patients; no real hospital systems.</div>'),
    ])


def flow_tab():
    return html.Div([
        dcc.Loading(html.Div(id="flow-bands"), type="dot"),
        H('<div class="ov-band"><div class="ov-k">Follow one question</div>'
          '<div class="ov-h">&ldquo;Is the prescription drafted now safe for her?&rdquo;</div>'
          '<div class="ov-s">The same question taken apart: each step run on its own against the system that holds the data, then all of it '
          'as the one certified view the live demo uses. Times are measured now.</div></div>'),
        html.Button("Run the trace, step by step", id="flow-trace", className="btn on", n_clicks=0),
        dcc.Loading(html.Div(id="flow-out"), type="dot"),
    ])


TAB = {"style": {}, "selected_style": {}, "className": "tab", "selected_className": "tab--selected"}


def create_dash_app(server, url_base_pathname, metadata):
    app = Dash(__name__, server=server, routes_pathname_prefix="/",
               requests_pathname_prefix=url_base_pathname.rstrip("/") + "/",
               assets_folder=str(HERE / "assets"), title="One patient, every branch — Exasol",
               suppress_callback_exceptions=True, index_string=INDEX)
    C.bind(server, metadata, __file__, load_rows, has_error)

    app.layout = html.Div(className="page", children=[
        H(f'<div class="pagehead">{_logo()}<span class="ph-t">Hospital group &middot; one patient, every branch &middot; live demo</span></div>'),
        html.Div(id="hero", children=H(hero({k: True for k in C.HEALTH}))),
        dcc.Interval(id="tick", interval=60_000, n_intervals=0),
        dcc.Store(id="active"), dcc.Store(id="scan-rows"), dcc.Store(id="ag-user", data=next(iter(ag.PEOPLE))),
        dcc.Store(id="ag-res", data={}), dcc.Store(id="ag-nores", data={}),
        dcc.Tabs(id="tabs", value="over", className="tabbar", parent_className="tabs-wrap", children=[
            dcc.Tab(label="1 · Overview", value="over", children=dcc.Loading(html.Div(id="ov-body"), type="dot"), **TAB),
            dcc.Tab(label="2 · Live demo", value="demo", children=demo_tab(), **TAB),
            dcc.Tab(label="3 · Who is asking", value="agent", children=agent_tab(), **TAB),
            dcc.Tab(label="4 · How it works", value="flow", children=flow_tab(), **TAB),
        ]),
        # on every tab: what this is and is not
        H('<div class="footnote" style="margin:1.4rem 0 .6rem">A fictional hospital chain with synthetic patients. '
          'An illustration of a data architecture, not clinical decision support.</div>'),
    ])

    @app.callback(Output("hero", "children"), Input("tick", "n_intervals"))
    def _hero(_):
        return H(hero(health()))

    @app.callback(Output("ov-body", "children"), Input("tabs", "value"), State("ov-body", "children"))
    def _overview(tab, have):
        if tab != "over" or have:
            return no_update
        return overview()

    # ---- live demo: a click lights the diagram at once; the answer follows
    @app.callback(Output("active", "data"), Output("dgm", "children"), Output("legend", "children"),
                  Output({"type": "q", "k": ALL}, "className"), Output("sim-box", "style"),
                  Input({"type": "q", "k": ALL}, "n_clicks"), prevent_initial_call=True)
    def _pick(_):
        k = ctx.triggered_id["k"]
        cls = ["btn wide" + (" on" if q == k else "") for q in C.QUESTIONS]
        return ({"k": k, "t": time.time()}, H(C.diagram(k)), H(C.legend(k)), cls,
                {"display": "grid"} if k == "similar" else {"display": "none"})

    @app.callback(Output("answer", "children"), Output("scan-rows", "data"),
                  Input("active", "data"), Input("sim-go", "n_clicks"), Input("sim-text", "value"),
                  State("active", "data"), prevent_initial_call=True)
    def _answer(_a, _go, _txt, active):
        if not active:
            return no_update, no_update
        k = active["k"]
        if ctx.triggered_id in ("sim-go", "sim-text") and k != "similar":
            return no_update, no_update
        out = C.run_question(k, text=_txt if k == "similar" else "")
        head, vis = C.answer_head(k, out)
        body = [H(head)]
        if k == "scans":
            body += scan_cards(out)
        body += [H(vis), H(C.answer_tail(k))]
        return [html.Div(className="ans", children=body), engineers(k, out)], (out["main"]["rows"] if k == "scans" else no_update)

    @app.callback(Output({"type": "rout", "i": MATCH}, "children"), Output({"type": "rimg", "i": MATCH}, "children"),
                  Input({"type": "render", "i": MATCH}, "n_clicks"), State("scan-rows", "data"), prevent_initial_call=True)
    def _render(_, rows):
        i = ctx.triggered_id["i"]
        r = scans.render(rows[i]["S3_KEY"])
        img = [html.Img(src=r["img"], alt="rendered from DICOM"), html.Div("rendered here, from the DICOM file", className="il")] if r.get("img") else None
        return render_steps(r), img

    @app.callback(Output({"type": "explain-out", "k": MATCH}, "children"), Input({"type": "explain", "k": MATCH}, "n_clicks"),
                  prevent_initial_call=True)
    def _explain(_):
        return html.Pre(C.explain_pg(ctx.triggered_id["k"]), className="sql")

    # ---- who is asking
    @app.callback(Output("ag-user", "data"), Output({"type": "who", "u": ALL}, "className"),
                  Input({"type": "who", "u": ALL}, "n_clicks"), prevent_initial_call=True)
    def _who(_):
        u = ctx.triggered_id["u"]
        return u, ["btn sm" + (" on" if x == u else " ghost") for x in ag.PEOPLE]

    @app.callback(Output("ag-res", "data"), Input("ag-ask", "n_clicks"), State("ag-user", "data"), State("ag-res", "data"),
                  prevent_initial_call=True)
    def _ask(_, u, res):
        res = dict(res or {})
        res[u] = ag.ask_or_cached(u)
        return res

    @app.callback(Output("ag-nores", "data"), Input("ag-bypass", "n_clicks"), State("ag-user", "data"), State("ag-nores", "data"),
                  prevent_initial_call=True)
    def _bypass(_, u, res):
        res = dict(res or {})
        try:
            res[u] = ag.bypass(u)
        except Exception as e:  # noqa: BLE001
            res[u] = {"error": True, "text": str(e)[:200], "secs": 0}
        return res

    @app.callback(Output("ag-head", "children"), Output("ag-out", "children"), Output("ag-cmp", "children"), Output("ag-no", "children"),
                  Input("ag-user", "data"), Input("ag-res", "data"), Input("ag-nores", "data"))
    def _agent_view(u, res, nores):
        done = (res or {}).get(u)
        head = H(f'<div class="ag-who">Question from <b>{ag.PEOPLE[u][0]}</b>: &ldquo;{ag.QUESTION}&rdquo;'
                 f'<div class="u">The AI client connects through the Exasol MCP server as database user {u}</div></div>' + ag.flow(u, bool(done)))
        out = None
        if done:
            cached = "" if done.get("live") else f'<div class="cached">Live source unavailable: showing the last good run. ({C.esc(done.get("error", ""))[:120]})</div>'
            db_secs = sum(x.get("secs", 0) for x in done.get("steps", []))
            out = html.Div([H(cached), html.Div(className="two even", children=[
                H('<div class="qk">What the agent did, step by step</div>' + ag.steps_html(done)),
                H(f'<div class="ans"><div class="q">{ag.QUESTION}</div><div class="src">Answered as {u} through the Exasol MCP server, '
                  f'{done.get("secs", 0):.1f} s end to end, of which {db_secs:.1f} s in the database '
                  f'(the rest is starting the MCP server)</div>{ag.answer_html(done, C.big3)}</div>')]),
                html.Details(className="eng", children=[html.Summary("The SQL that produced this answer (replay it next week, same person, same rules)"),
                                                        html.Pre(ag.SQL_TOP, className="sql")])])
        cmp_ = None
        a, b = (res or {}).get("HOSP_DR_BRB"), (res or {}).get("HOSP_QUALITY_ANALYST")
        if a and b:
            def _n(o):
                t = o.get("top") or []
                return int((t[0] if t else {}).get("ALERTS") or 0), sum(1 for r in t if str(r.get("PATIENT_NAME", "")).startswith("Patient "))
            (na, _ma), (nb, mb) = _n(a), _n(b)
            cmp_ = H('<div class="qk" style="margin-top:.8rem">Same question, same SQL, two people</div><div class="ag-cmp">'
                     f'<div class="c"><div class="l">{ag.PEOPLE["HOSP_DR_BRB"][0]}</div><div class="v">{na} alerts &middot; names shown</div><div class="l">patients registered in Branch B, with their full history from every branch</div></div>'
                     f'<div class="c"><div class="l">{ag.PEOPLE["HOSP_QUALITY_ANALYST"][0]}</div><div class="v">{nb} alerts &middot; {mb} pseudonyms</div><div class="l">every branch, no identities</div></div></div>'
                     '<div class="hint">The rule lives in the engine, so every assistant inherits it. Nobody re-implements it per tool.</div>')
        no = (nores or {}).get(u)
        nodiv = None
        if no:
            msg = no.get("text", "")
            if "privilege" in msg.lower():
                msg = msg.split("rejected the query:")[-1].split("(Session")[0].strip() if "rejected" in msg else msg
                nodiv = H(f'<div class="ag-no"><b>Refused by Exasol.</b> {C.esc(ag.SQL_BYPASS.split("--")[0].strip())} &rarr; {C.esc(msg)}. '
                          'The rule is in the database, not in the prompt.</div>')
            else:
                nodiv = H('<div class="cached">Could not reach the database just now, so this is not a refusal. Check <code>exakit status</code>, then click again.</div>')
        return head, out, cmp_, nodiv

    @app.callback(Output("ag-aud", "children"), Input("ag-audit", "n_clicks"), prevent_initial_call=True)
    def _audit(_):
        aud = C.run("agent_audit")
        ok = lambda r: str(r["SUCCESS"]).lower() in ("true", "1")  # noqa: E731
        rows = "".join(f'<tr><td><b>{C.esc(r["USER_NAME"])}</b></td><td>{C.esc(str(r["START_TIME"])[:19])}</td>'
                       f'<td class="{"ok" if ok(r) else "f"}">{"ran" if ok(r) else "REFUSED"}</td>'
                       f'<td>{r["SECS"]}</td><td><code>{C.esc(r["SQL_TEXT"])}</code></td></tr>' for r in aud["rows"])
        return H(f'<div class="ag-aud"><table><tr><th>Who</th><th>When</th><th></th><th>Seconds</th><th>SQL</th></tr>{rows}</table></div>'
                 + ("" if aud.get("live") else '<div class="cached">Live source unavailable: showing the last good run.</div>'))

    # ---- how it works
    @app.callback(Output("flow-bands", "children"), Input("tabs", "value"), State("flow-bands", "children"))
    def _bands(tab, have):
        if tab != "flow" or have:
            return no_update
        c, s3n = flow_counts()
        c = (c["rows"] or [{}])[0]
        counts = {"legacy": int(c.get("LEGACY") or 0), "modern": int(c.get("MODERN") or 0), "records": int(c.get("RECORDS") or 0),
                  "people": int(c.get("PEOPLE") or 0), "review": int(c.get("REVIEW") or 0), "notes": int(c.get("NOTES") or 0),
                  "vectors": int(c.get("VECTORS") or 0), "studies": sum(int(r["STUDIES"]) for r in s3n["rows"]),
                  "mb": sum(float(r["BYTES"] or 0) for r in s3n["rows"]) / 1e6}
        return html.Div([H(how.page(counts["records"] or 1609, counts["people"] or 1224)),
                         html.Details(className="hw-more", children=[html.Summary("For engineers: every step, set up once and per question")]
                                      + [H(flow.setup_band(counts)), H(flow.query_band())])])

    @app.callback(Output("flow-out", "children"), Input("flow-trace", "n_clicks"), prevent_initial_call=True)
    def _trace(_):
        res = {k: C.run(f"flow_{k}") for k in C.TRACE_SQL}
        kids = [H(flow.trace_html(res))]
        if not all(r["live"] for r in res.values()):
            kids.append(H('<div class="cached">A source was unavailable: some steps show the last good run.</div>'))
        kids.append(html.Details(className="eng", children=[html.Summary("For engineers: the five statements")]
                                 + [html.Pre(q, className="sql") for q in C.TRACE_SQL.values()]))
        return kids

    return app
