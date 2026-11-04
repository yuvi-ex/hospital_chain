"""Tab 4 · How it works: the flow diagram, in two bands, plus one question traced step by step with measured times.

Band 1 is everything done once (and refreshed nightly); band 2 is what every question touches. The split is the
architectural claim: the expensive work happens ahead of time, a question only ever reads.
Built from HTML boxes rather than a hand-placed SVG, so it cannot overlap and it reflows on a narrow screen.
"""
import html as _h

CSS = """<style>
.fw-band { border-radius:22px; border:1px solid var(--edge); background:#fff; box-shadow:var(--shadow); padding:1rem 1.2rem 1.1rem; margin:.8rem 0 1rem; }
.fw-band.q { background:linear-gradient(180deg,#F2FBF9 0%,#fff 60%); border-color:#CDEBE4; }
.fw-bh { display:flex; align-items:baseline; gap:.8rem; flex-wrap:wrap; margin-bottom:.6rem; }
.fw-bh .k { text-transform:uppercase; letter-spacing:.14em; font-size:.7rem; font-weight:800; color:#fff; background:var(--ink2); border-radius:999px; padding:.25rem .75rem; }
.fw-band.q .fw-bh .k { background:#12796A; }
.fw-bh .t { font-weight:800; font-size:1.15rem; color:var(--ink2); } .fw-bh .s { font-size:.88rem; color:var(--muted); }
.fw-lane { display:grid; grid-template-columns:11rem minmax(0,1fr); gap:.9rem; align-items:center; padding:.55rem 0; border-top:1px dashed var(--edge); }
.fw-lane:first-of-type { border-top:0; }
.fw-ln .l { display:inline-flex; width:1.7rem; height:1.7rem; border-radius:50%; background:var(--ink2); color:#fff; font-weight:900; font-size:.85rem;
  align-items:center; justify-content:center; margin-bottom:.25rem; }
.fw-ln .n { font-weight:800; font-size:.98rem; color:var(--ink2); } .fw-ln .d { font-size:.78rem; color:var(--muted); line-height:1.35; margin-top:.1rem; }
.fw-row { display:flex; align-items:stretch; gap:0; }
.fw-box { flex:1; min-width:0; border-radius:14px; border:1px solid var(--edge); background:#fff; padding:.55rem .7rem; }
.fw-box .h { font-weight:800; font-size:.88rem; color:var(--ink2); line-height:1.25; }
.fw-box .d { font-size:.76rem; color:var(--muted); line-height:1.35; margin-top:.15rem; }
.fw-box .c { display:inline-block; font-family:'JetBrains Mono',monospace; font-size:.66rem; color:#0076AD; background:#E2F4FF; border-radius:6px; padding:.05rem .35rem; margin-top:.3rem; }
.fw-box.src { border-left:4px solid #9FB0C4; } .fw-box.src.pg { border-left-color:#C56A00; } .fw-box.src.mg { border-left-color:#0076AD; } .fw-box.src.s3 { border-left-color:#5B5FE0; }
.fw-box.exa { background:#F2FBF9; border-color:#9ED9CE; } .fw-box.sem { background:#F5F6FF; border-color:#C9CCF7; }
.fw-box.out { background:#E2F4FF; border-color:#7CC8F0; } .fw-box.out .h { color:#0B1B34; } .fw-box.out .d { color:#0076AD; }
.fw-band.q .fw-row { align-items:center; }
.fw-box .tag { float:right; font-size:.58rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; color:var(--faint); }
.fw-ar { flex:0 0 1.9rem; display:flex; align-items:center; justify-content:center; color:#12796A; font-weight:900; font-size:1.15rem; }
.fw-fan { flex:1.15; display:grid; gap:.35rem; min-width:0; }
.fw-fan .fw-box { flex:none; padding:.4rem .6rem; }
.fw-note { display:flex; gap:.6rem; flex-wrap:wrap; margin-top:.7rem; }
.fw-note div { flex:1; min-width:16rem; border-radius:12px; background:#F6F9FC; border:1px dashed #C9D3E0; padding:.5rem .7rem; font-size:.82rem; color:var(--ink2); line-height:1.4; }
.fw-note b { color:#12796A; }
.fw-tr { display:grid; grid-template-columns:2rem minmax(0,1.3fr) 7.5rem minmax(0,1.6fr) 4.5rem 4.5rem; gap:.6rem; align-items:center;
  padding:.5rem .7rem; border-bottom:1px solid #EEF2F7; font-size:.86rem; }
.fw-tr.h { font-size:.62rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); }
.fw-tr .i { width:1.6rem; height:1.6rem; border-radius:50%; background:#12796A; color:#fff; font-weight:800; font-size:.78rem; display:flex; align-items:center; justify-content:center; }
.fw-tr .w { font-weight:800; } .fw-tr .r { font-size:.8rem; color:var(--muted); line-height:1.35; }
.fw-tr .num { text-align:right; font-variant-numeric:tabular-nums; font-weight:800; }
.fw-tr .sb { font-size:.62rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; border-radius:8px; padding:.2rem .4rem; text-align:center; }
.sb.pg { background:#FFF4E5; color:#9A4A00; } .sb.mg { background:#E2F4FF; color:#0076AD; } .sb.ex { background:#E3F5F1; color:#12796A; } .sb.s3 { background:#EEF0FF; color:#3B3FB8; }
.fw-tr.tot { background:#F6F9FC; font-weight:800; border-bottom:0; }
@media (max-width:1200px) { .fw-lane { grid-template-columns:1fr; } .fw-row { flex-wrap:wrap; gap:.4rem; } .fw-ar { display:none; }
  .fw-box, .fw-fan { flex:1 1 45%; } .fw-tr { grid-template-columns:2rem 1fr 6rem; } .fw-tr > :nth-child(4), .fw-tr > :nth-child(5) { display:none; } }
</style>"""


def box(h, d="", code="", cls="", tag=""):
    t = f'<span class="tag">{tag}</span>' if tag else ""
    c = f'<div class="c">{code}</div>' if code else ""
    return f'<div class="fw-box {cls}">{t}<div class="h">{h}</div>{f"<div class='d'>{d}</div>" if d else ""}{c}</div>'


AR = '<div class="fw-ar">&rarr;</div>'


def chain(*items):
    return '<div class="fw-row">' + AR.join(items) + "</div>"


def lane(letter, name, desc, row):
    return (f'<div class="fw-lane"><div class="fw-ln"><span class="l">{letter}</span><div class="n">{name}</div>'
            f'<div class="d">{desc}</div></div>{row}</div>')


def setup_band(n):
    """n: live counts (records, people, notes, vectors, studies, mb)."""
    a = chain(box("Both branch systems", f'{n["legacy"]:,} HIS + {n["modern"]:,} EHR patient records, read live', cls="src pg", tag="Postgres + MongoDB"),
              box("Matching rules in SQL", "given name, surname or initial, birth date (also day/month swapped), mobile", cls="exa"),
              box("Patient index", f'{n["records"]:,} records &rarr; {n["people"]:,} people, a reason on every link', "HOSP_CORE.MPI", cls="exa"),
              box("Review queue", f'{n["review"]} borderline pairs go to a person, never to a guess', "MATCH_REVIEW_QUEUE", cls="exa"))
    b = chain(box("Clinical notes", f'{n["notes"]:,} discharge summaries (HIS) and admission notes (EHR)', cls="src mg", tag="both systems"),
              box("Embedded once, offline", "bge-small model, 384 numbers per note; the same model embeds a typed question", cls=""),
              box("Note vectors in Exasol", f'{n["vectors"] / 1e6:.1f} M rows, long and narrow: similarity is a join + GROUP BY', "HOSP_CORE.NOTE_VECTORS", cls="exa"),
              box("Text stays at the source", "Exasol keeps the key and the vector; the note is read live when shown", cls="exa"))
    c = chain(box("Scanners write DICOM", "X-ray, CT and MRI, each file with a header: patient ID, date, body part", cls="src s3", tag="PACS"),
              box("Files on Amazon S3", f'{n["studies"]} studies, {n["mb"]:.0f} MB, never copied into the database', "s3://…/pacs/", cls="src s3"),
              box("Header index beside them", "one row per study, read in place on every query", "index/dicom_index.csv", cls="src s3"),
              box("Read-only key", "one IAM user, GetObject and ListBucket on this bucket only", "CONNECTION HOSP_S3", cls="exa"))
    d = chain(box("Certified definitions", "patient, readmission, drug conflict: written once, in the view", "HOSP_GOV.*", cls="sem"),
              box("Access map", "per person: which branch, and full identity or masked", "ACCESS_MAP", cls="sem"),
              box("Named users, one role", "doctor and analyst can read the views and nothing else", "HOSP_AGENT_READER", cls="sem"),
              box("Audit log", "every statement, who ran it, whether it was refused", "EXA_DBA_AUDIT_SQL", cls="sem"))
    return f'''<div class="fw-band"><div class="fw-bh"><span class="k">Set up once</span><span class="t">Before anyone asks</span>
      <span class="s">refreshed nightly in production; nothing here is on the path of a question</span></div>
      {lane("A", "Who is who", "the same person under different IDs", a)}
      {lane("B", "What notes mean", "so similar cases can be found by meaning", b)}
      {lane("C", "Where images are", "the archive stays a file store", c)}
      {lane("D", "Who may see what", "the rules live in the engine", d)}</div>'''


def query_band():
    fan = ('<div class="fw-fan">'
           + box("A &middot; Legacy HIS", "the query is translated to Postgres SQL and runs there", cls="src pg", tag="Postgres")
           + box("B &middot; Modern EHR", "a find on the documents; nested arrays come back as rows", cls="src mg", tag="MongoDB")
           + box("C &middot; PACS index", "one signed GET for the header index", cls="src s3", tag="S3")
           + "</div>")
    row = chain(box("1 &middot; A person or an agent", "clinician, analyst, or an AI client through the Exasol MCP server", cls="out"),
                box("2 &middot; Governed view", "row filter by CURRENT_USER, identity masked if required", "HOSP_GOV", cls="sem"),
                box("3 &middot; Patient index", "every record of the person, from every system", "UNIFIED_ID", cls="exa"),
                box("4 &middot; Virtual schemas", "each source is asked only for what this question needs", cls="exa"),
                fan,
                box("5 &middot; Exasol joins", "orders &times; allergies, notes &times; vectors (GROUP BY), outcomes", cls="exa"),
                box("6 &middot; The answer", "plus the SQL that produced it, and a row in the audit log", cls="out"))
    return f'''<div class="fw-band q"><div class="fw-bh"><span class="k">Every question</span><span class="t">Live, in about a second</span>
      <span class="s">read-only, at the source, nothing copied</span></div>{row}
      <div class="fw-note">
        <div><b>Images</b> go straight from S3 to the browser by a signed link that expires in 15 minutes. No pixels pass through the database.</div>
        <div><b>Hot paths</b> are copied once into Exasol (HOSP_ACCEL) when they prove worth it: the same SQL, about 0.01 s instead of 1 s, the same answer.</div>
        <div><b>An AI agent</b> takes the same path as a person: the same views, the same rules, the same audit log. Nobody re-implements access per tool.</div></div></div>'''


TRACE = [  # (source badge class, badge, what, sql key)
    ("ex", "Exasol", "Find every record of her", "t_mpi"),
    ("mg", "MongoDB", "Read today's orders in Branch B", "t_orders"),
    ("pg", "Postgres", "Read her allergy notes in Branch A", "t_allergy"),
    ("ex", "Exasol", "Look up the drug class", "t_class"),
    ("ex", "Exasol + both", "All of it as one certified view", "t_all"),
]


def trace_sql(hero_ehr, legacy_id):
    me = f"(SELECT UNIFIED_ID FROM HOSP_CORE.MPI WHERE RECORD_ID = '{hero_ehr}')"
    return {
        "t_mpi": f"SELECT RECORD_ID, SOURCE_SYSTEM, LINK_SCORE FROM HOSP_CORE.MPI WHERE UNIFIED_ID = {me}",
        "t_orders": f"SELECT DRUG, DOSE, ORDER_STATUS FROM HOSP_SRC.MODERN_MEDICATIONS WHERE RECORD_ID = '{hero_ehr}' AND ORDER_STATUS IN ('draft', 'active')",
        "t_allergy": f"SELECT ALLERGY_AS_RECORDED, DRUG_CLASS, SEVERITY FROM HOSP_SRC.LEGACY_ALLERGIES WHERE RECORD_ID = '{legacy_id}'",
        "t_class": "SELECT DRUG, DRUG_CLASS FROM HOSP_CORE.DRUG_CLASS WHERE DRUG = 'AMOXICILLIN-CLAVULANATE'",
        "t_all": f"SELECT DRUG, ALLERGY_AS_RECORDED, KNOWN_WHERE_PRESCRIBED FROM HOSP_CORE.ALLERGY_CONFLICTS WHERE UNIFIED_ID = {me}",
    }


def _summary(key, rows):
    if not rows:
        return "no rows"
    r = rows[0]
    if key == "t_mpi":
        return " &middot; ".join(f'{_h.escape(str(x["RECORD_ID"]))} ({"HIS" if x["SOURCE_SYSTEM"] == "LEGACY_HIS" else "EHR"})' for x in rows)
    if key == "t_orders":
        return " &middot; ".join(f'{_h.escape(str(x["DRUG"]))} ({_h.escape(str(x["ORDER_STATUS"]))})' for x in rows)
    if key == "t_allergy":
        return f'&ldquo;{_h.escape(str(r["ALLERGY_AS_RECORDED"]))}&rdquo; &rarr; {_h.escape(str(r["DRUG_CLASS"]))}, {_h.escape(str(r["SEVERITY"]))}'
    if key == "t_class":
        return f'{_h.escape(str(r["DRUG"]).capitalize())} is a {_h.escape(str(r["DRUG_CLASS"]).lower())}'
    return f'<b style="color:#C8102E">conflict:</b> {_h.escape(str(r["DRUG"]))} &times; {_h.escape(str(r["ALLERGY_AS_RECORDED"]))}'


def trace_html(results):
    head = ('<div class="fw-tr h"><div></div><div>Step</div><div>Where it runs</div><div>What came back</div>'
            '<div style="text-align:right">Rows</div><div style="text-align:right">Seconds</div></div>')
    rows, tot = "", 0.0
    for i, (cls, badge, what, key) in enumerate(TRACE, 1):
        res = results.get(key) or {"rows": [], "secs": 0}
        tot += res["secs"] if i < len(TRACE) else 0
        rows += (f'<div class="fw-tr"><div class="i">{i}</div><div class="w">{what}</div><div class="sb {cls}">{badge}</div>'
                 f'<div class="r">{_summary(key, res["rows"])}</div><div class="num">{len(res["rows"])}</div>'
                 f'<div class="num">{res["secs"]:.2f}</div></div>')
    last = results.get("t_all") or {"secs": 0}
    rows += (f'<div class="fw-tr tot"><div></div><div>Steps 1-4, for her only</div><div></div><div class="r">'
             f'Step 5 takes {last["secs"]:.2f} s because it checks every current order in the chain, then keeps her row: '
             f'the same view answers question 6</div><div></div><div class="num">{tot:.2f}</div></div>')
    return f'<div class="fw-band" style="padding:.4rem .3rem">{head}{rows}</div>'
