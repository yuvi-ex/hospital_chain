"""Hospital-chain demo: the control room (the Streamlit fallback console).

Run:  app/run.sh   ->  http://localhost:8515 (HC_STREAMLIT_PORT)
A hospital chain with a legacy branch (Postgres HIS), a modern branch (MongoDB EHR) and imaging on Amazon S3.
Left: the live architecture. Right: six plain-English questions about one patient and then the whole chain.
Clicking one lights the path it takes, runs it live, and shows the answer, three numbers and what Exasol did.
The SQL is one click away ("For engineers") and nowhere else.
"""
import base64
import html as _h
import json
from pathlib import Path

import streamlit as st

import db
import hcconfig as C
from page_css import PAGE_CSS
from theme import CSS

st.set_page_config(page_title="One patient, every branch — Exasol", layout="wide", initial_sidebar_state="collapsed")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SQLDIR = ROOT / "sql"
ss = st.session_state
BUCKET, REGION = C.S3_BUCKET, C.S3_REGION
HERO_EHR, HERO_NOTE = "BRB-P-108842", "M:ENC-BRB-2610-02605"


def html(fragment: str, target=st) -> None:
    """Collapse blank lines so Streamlit's markdown pass cannot end the HTML block."""
    target.markdown("\n".join(l for l in fragment.splitlines() if l.strip()), unsafe_allow_html=True)


html(CSS)
html(PAGE_CSS)
html("""<style>
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
.scans { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.7rem; margin:.4rem 0; }
.scan { border-radius:16px; border:1px solid var(--edge); background:#0B0F17; overflow:hidden; }
.scan img { display:block; width:100%; height:230px; object-fit:contain; background:#000; }
.scan .cap { background:#fff; padding:.5rem .7rem; font-size:.82rem; } .scan .cap b { color:var(--ink2); }
.scan .cap .m { font-family:'JetBrains Mono',monospace; font-size:.7rem; color:var(--faint); margin-top:.15rem; word-break:break-all; }
.scan .cap a { font-size:.74rem; font-weight:800; color:#0076AD; text-decoration:none; }
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
</style>""")


def _logo() -> str:
    b64 = base64.b64encode((HERE / "assets" / "exasol_logo_dark.svg").read_bytes()).decode()
    return (f'<img src="data:image/svg+xml;base64,{b64}" alt="Exasol" width="104" height="26" '
            f'style="height:26px;width:auto;max-width:104px;display:block;"/>')


# ------------------------------------------------------------------ SQL (shown only to engineers)
ME = f"(SELECT UNIFIED_ID FROM HOSP_CORE.MPI WHERE RECORD_ID = '{HERO_EHR}')"
Q_WHO = f"""-- every record the chain holds for her, read live from each system and tied together by the patient index
SELECT 'Legacy HIS' AS SOURCE_LABEL, l.BRANCH, l.RECORD_ID, l.NAME_AS_RECORDED, l.BIRTH_DATE_AS_RECORDED, l.MOBILE, m.LINK_SCORE, m.MATCH_REASON
FROM   HOSP_SRC.LEGACY_PATIENTS l                      -- Postgres, Branch A (virtual schema)
JOIN   HOSP_CORE.MPI m ON m.RECORD_ID = l.RECORD_ID
WHERE  m.UNIFIED_ID = {ME}
UNION ALL
SELECT 'Modern EHR', p.BRANCH, p.RECORD_ID, p.NAME_AS_RECORDED, p.BIRTH_DATE_AS_RECORDED, p.MOBILE, m.LINK_SCORE, m.MATCH_REASON
FROM   HOSP_SRC.MODERN_PATIENTS p                      -- MongoDB, Branch B (virtual schema)
JOIN   HOSP_CORE.MPI m ON m.RECORD_ID = p.RECORD_ID
WHERE  m.UNIFIED_ID = {ME}
UNION ALL
SELECT 'PACS on S3', i.INSTITUTION, i.PATIENT_ID, i.PATIENT_NAME, i.PATIENT_BIRTH_DATE, NULL, NULL, i.STUDY_DESCRIPTION || ' · ' || i.STUDY_DATE
FROM   HOSP_SRC.IMAGING_INDEX i                        -- DICOM header index on S3, read in place
JOIN   HOSP_CORE.MPI m ON m.PACS_PATIENT_ID = i.PATIENT_ID
WHERE  m.UNIFIED_ID = {ME}"""

Q_ALLERGY = f"""-- a CURRENT order (draft or active) in any system x an allergy recorded for the same PERSON in any system
SELECT DRUG, DOSE, ORDER_STATUS, PRESCRIBED_IN, PRESCRIBED_UNDER, DRUG_CLASS,
       ALLERGY_AS_RECORDED, SEVERITY, ALLERGY_RECORDED_IN, ALLERGY_RECORD_ID, KNOWN_WHERE_PRESCRIBED
FROM   HOSP_CORE.ALLERGY_CONFLICTS                     -- MongoDB orders x Postgres allergy notes, through the patient index
WHERE  UNIFIED_ID = {ME}"""
Q_ALLERGY_EHR = f"""SELECT ALLERGIES_RECORDED FROM HOSP_SRC.MODERN_PATIENTS WHERE RECORD_ID = '{HERO_EHR}'"""
Q_ALLERGY_NOTE = f"""-- the 2019 discharge summary in the legacy HIS, read live
SELECT v.VISIT_NO, v.ADM_DT, s.SUMM_TXT
FROM   HOSP_LEGACY.DIS_SUMM s JOIN HOSP_LEGACY.VISIT_HDR v ON v.VISIT_NO = s.VISIT_NO
JOIN   HOSP_CORE.MPI m ON m.RECORD_ID = v.PAT_NO
WHERE  m.UNIFIED_ID = {ME} AND s.SUMM_TXT LIKE '%ANAPHYLAXIS%'"""

Q_SCANS = f"""SELECT STUDY_DATE, MODALITY, BODY_PART, STUDY_DESCRIPTION, INSTITUTION, PACS_PATIENT_ID, NAME_IN_DICOM,
       ACCESSION_NUMBER, S3_KEY, THUMB_KEY, FILE_BYTES
FROM   HOSP_CORE.IMAGING_STUDIES                       -- header index on S3 x patient index
WHERE  UNIFIED_ID = {ME}
ORDER  BY STUDY_DATE"""
Q_SCANS_ALL = """SELECT MODALITY, COUNT(*) AS STUDIES, SUM(FILE_BYTES) AS BYTES FROM HOSP_SRC.IMAGING_INDEX GROUP BY MODALITY"""


def q_similar(vector_sql=None, pen_only=True):
    q = vector_sql or f"SELECT DIM, VAL FROM HOSP_CORE.NOTE_VECTORS WHERE NOTE_ID = '{HERO_NOTE}'"
    return f"""WITH q AS ({q}),                       -- {"the typed text, embedded by the same model" if vector_sql else "her admission note from today"}
sim AS (SELECT v.NOTE_ID, SUM(v.VAL * q.VAL) AS SIMILARITY       -- cosine similarity = join + GROUP BY
        FROM HOSP_CORE.NOTE_VECTORS v JOIN q ON q.DIM = v.DIM GROUP BY v.NOTE_ID),
cases AS (SELECT n.UNIFIED_ID, n.ENCOUNTER_ID, s.SIMILARITY FROM sim s JOIN HOSP_CORE.NOTES n ON n.NOTE_ID = s.NOTE_ID
          WHERE n.UNIFIED_ID <> {ME}),
abx AS (SELECT ENCOUNTER_ID, DRUG FROM HOSP_CORE.MEDICATIONS                  -- both systems, live
        WHERE UPPER(DRUG) IN ('AMOXICILLIN-CLAVULANATE', 'AMOXICILLIN', 'AMPICILLIN', 'PIPERACILLIN-TAZOBACTAM', 'LEVOFLOXACIN',
                              'DOXYCYCLINE', 'AZITHROMYCIN', 'CEFTRIAXONE', 'CLARITHROMYCIN')),
pen AS (SELECT UNIFIED_ID FROM HOSP_CORE.ALLERGIES WHERE DRUG_CLASS = 'PENICILLIN' GROUP BY UNIFIED_ID),
readm AS (SELECT PREV_ENCOUNTER_ID FROM HOSP_CORE.READMISSIONS_30D GROUP BY PREV_ENCOUNTER_ID)
SELECT c.UNIFIED_ID, FLOOR(YEARS_BETWEEN(CURRENT_DATE, p.BIRTH_DATE)) AS AGE, e.BRANCH, e.SOURCE_SYSTEM, e.DIAGNOSIS, e.ADMIT_DATE,
       e.LENGTH_OF_STAY, ROUND(c.SIMILARITY, 3) AS SIMILARITY, a.DRUG AS ANTIBIOTIC,
       CASE WHEN pen.UNIFIED_ID IS NULL THEN FALSE ELSE TRUE END AS PENICILLIN_ALLERGY,
       CASE WHEN r.PREV_ENCOUNTER_ID IS NULL THEN FALSE ELSE TRUE END AS READMITTED_30D
FROM   cases c
JOIN   HOSP_CORE.ENCOUNTERS e ON e.ENCOUNTER_ID = c.ENCOUNTER_ID AND e.ENCOUNTER_CLASS = 'inpatient' AND e.STATUS = 'finished'
JOIN   HOSP_CORE.PATIENT_SUMMARY p ON p.UNIFIED_ID = c.UNIFIED_ID
JOIN   HOSP_CORE.DIABETIC_PATIENTS d ON d.UNIFIED_ID = c.UNIFIED_ID           -- diabetic in EITHER system
{"JOIN" if pen_only else "LEFT JOIN"}   pen ON pen.UNIFIED_ID = c.UNIFIED_ID                            -- penicillin allergy, recorded in either system
LEFT JOIN abx a ON a.ENCOUNTER_ID = c.ENCOUNTER_ID
LEFT JOIN readm r ON r.PREV_ENCOUNTER_ID = c.ENCOUNTER_ID
WHERE  YEARS_BETWEEN(CURRENT_DATE, p.BIRTH_DATE) >= 60
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.UNIFIED_ID ORDER BY c.SIMILARITY DESC) = 1    -- best match per patient
ORDER  BY c.SIMILARITY DESC
LIMIT  6"""


Q_READM_SHAPE = """SELECT BRANCH, COUNT(*) AS READMISSIONS, SUM(CASE WHEN VISIBLE_TO_ONE_SYSTEM THEN 0 ELSE 1 END) AS HIDDEN
FROM   {src}
GROUP  BY BRANCH ORDER BY BRANCH"""
Q_READM_LIVE = "-- live: Postgres + MongoDB through the patient index, nothing copied\n" + Q_READM_SHAPE.format(src="HOSP_CORE.READMISSIONS_30D")
Q_READM_FAST = "-- on the copy inside Exasol (built once from the same live views)\n" + Q_READM_SHAPE.format(src="HOSP_ACCEL.READMISSIONS_30D")
Q_ACCEL = "CREATE OR REPLACE TABLE " + (SQLDIR / "50_accelerate.sql").read_text().split("CREATE OR REPLACE TABLE", 1)[1].split(";", 1)[0].strip()

Q_CHAIN = """-- every patient in a bed RIGHT NOW whose order contradicts an allergy recorded for the same person anywhere
SELECT p.PATIENT_NAME, FLOOR(YEARS_BETWEEN(CURRENT_DATE, p.BIRTH_DATE)) AS AGE, c.ENCOUNTER_ID, c.PRESCRIBED_IN,
       c.DRUG, c.ORDER_STATUS, c.ALLERGY_AS_RECORDED, c.SEVERITY, c.ALLERGY_RECORDED_IN, c.KNOWN_WHERE_PRESCRIBED
FROM   HOSP_CORE.ALLERGY_CONFLICTS c                   -- MongoDB orders x Postgres + MongoDB allergies
JOIN   HOSP_CORE.PATIENT_SUMMARY p ON p.UNIFIED_ID = c.UNIFIED_ID
JOIN   HOSP_CORE.ENCOUNTERS e ON e.ENCOUNTER_ID = c.ENCOUNTER_ID AND e.STATUS = 'in-progress'
ORDER  BY c.KNOWN_WHERE_PRESCRIBED, c.SEVERITY DESC"""
Q_INBED = """SELECT STATUS, COUNT(*) AS PATIENTS FROM HOSP_SRC.MODERN_ENCOUNTERS WHERE STATUS = 'in-progress' GROUP BY STATUS"""


# ------------------------------------------------------------------ the six questions
QUESTIONS = {
    "who": dict(n=1, ask="Who is Meenakshi Sundaram, across every branch?", src="Legacy HIS (Postgres) + modern EHR (MongoDB) + PACS (S3), tied by the patient index",
                nodes={"exa", "pg", "mongo", "s3", "mpi"}, edges={"P", "M", "S"}, go="", back="",
                did=["Read her records live from three systems that have never shared an ID: the Branch A HIS, the Branch B EHR and the PACS.",
                     "Resolved them to one person with the patient index: deterministic rules, every link explained.",
                     "Three ways to write the same birth date and name, one answer. Nothing was copied to get it."]),
    "allergy": dict(n=2, ask="Is the prescription Branch B just drafted safe for her?", src="Draft order in MongoDB x allergy note in Postgres, read live",
                    nodes={"exa", "pg", "mongo", "mpi"}, edges={"P", "M"}, go="the question", back="1 alert",
                    did=["Read today's draft order from the Branch B EHR and her allergy history from the Branch A HIS, live, in one SQL statement.",
                         "Mapped both to drug classes (amoxicillin-clavulanate is a penicillin) with a formulary table in Exasol.",
                         "The Branch B system on its own holds no allergy for her. Only the fused record shows the conflict."]),
    "scans": dict(n=3, ask="What did her earlier scans show?", src="DICOM header index on Amazon S3, read in place; images shown from S3",
                  nodes={"exa", "s3", "mpi"}, edges={"S"}, go="read index", back="her studies",
                  did=["Read the PACS header index straight from S3 with a read-only key. No load job.",
                       "Matched the DICOM PatientID tags (two different ID schemes) to her through the patient index.",
                       "The images never pass through the database: the page shows them from S3 by signed link."]),
    "similar": dict(n=4, ask="Patients like her who were also penicillin-allergic: what worked?", src="Note vectors in Exasol + allergies and diabetes from both systems + outcomes",
                    nodes={"exa", "pg", "mongo", "vec", "mpi"}, edges={"P", "M"}, go="", back="",
                    did=["Ranked 3,976 clinical notes by similarity to her note from today: cosine similarity as a join and GROUP BY, inside Exasol.",
                         "Kept only diabetic patients over 60 with a penicillin allergy, using facts from BOTH branch systems, live.",
                         "Added what they were given and how it went (stay, readmission) from the system that treated them."]),
    "readmit": dict(n=5, ask="How many readmissions can no single branch see?", src="Encounters from both systems, live, then from Exasol's in-memory copy",
                    nodes={"exa", "pg", "mongo", "mpi"}, edges={"P", "M"}, via=set(), go="", back="",
                    did=["Applied ONE certified definition of a 30-day readmission to every branch: same person, any branch, any system.",
                         "A third of readmissions cross systems or branches, so each branch system alone under-counts them.",
                         "Asked again on a copy built once inside Exasol: same answer, a fraction of the time. Federate first, accelerate what earns it."]),
    "chain": dict(n=6, ask="Who else is in a bed right now with an order like hers?", src="Every current order in MongoDB x allergies in Postgres and MongoDB",
                  nodes={"exa", "pg", "mongo", "mpi"}, edges={"P", "M"}, go="", back="",
                  punch=("No pipeline was built for this question.", "Two branch systems, a patient index and one SQL statement found them.",
                         "Legacy + modern &middot; live &middot; zero migration"),
                  did=["Checked every current medication order in the chain against every allergy recorded for the same person, anywhere.",
                       "KNOWN_WHERE_PRESCRIBED = false: the prescribing system had no way to see the allergy.",
                       "The same view is the certified safety check the governed layer exposes (tab 3)."]),
}


def run_question(k):
    if k == "who":
        return {"main": db.run("laptop", Q_WHO, key="who")}
    if k == "allergy":
        return {"main": db.run("laptop", Q_ALLERGY, key="allergy"), "ehr": db.run("laptop", Q_ALLERGY_EHR, key="allergy_ehr"),
                "note": db.run("laptop", Q_ALLERGY_NOTE, key="allergy_note")}
    if k == "scans":
        return {"main": db.run("laptop", Q_SCANS, key="scans"), "all": db.run("laptop", Q_SCANS_ALL, key="scans_all")}
    if k == "similar":
        text = (ss.get("sim_text") or "").strip()
        if text:
            sql = q_similar(vector_sql=embed_values(text))
            return {"main": db.run("laptop", sql, key=None), "sql": sql, "text": text}
        sql = q_similar()
        return {"main": db.run("laptop", sql, key="similar"), "sql": sql}
    if k == "readmit":
        return {"main": db.run("laptop", Q_READM_LIVE, key="readm_live"), "fast": db.run("laptop", Q_READM_FAST, key="readm_fast")}
    return {"main": db.run("laptop", Q_CHAIN, key="chain"), "inbed": db.run("laptop", Q_INBED, key="inbed")}


@st.cache_resource(show_spinner=False)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding("BAAI/bge-small-en-v1.5")


def embed_values(text):
    """Typed text -> the same 384-d model the notes were embedded with -> a VALUES list the SQL joins on."""
    import numpy as np
    v = np.array(list(_model().embed([text.lower()]))[0], dtype=np.float64)
    v /= np.linalg.norm(v)
    rows = ", ".join(f"({i}, {x:.6f})" for i, x in enumerate(v))
    return f"SELECT DIM, VAL FROM VALUES {rows} AS t(DIM, VAL)"


@st.cache_resource(show_spinner=False)
def _s3():
    import boto3
    from botocore.config import Config
    # regional endpoint + SigV4: the global endpoint signs for us-east-1 and S3 answers SignatureDoesNotMatch
    cfg = dict(region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com",
               config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    key = C.S3_KEY_FILE
    if key.exists():                     # the same read-only identity Exasol uses
        k = json.loads(key.read_text())["AccessKey"]
        return boto3.client("s3", aws_access_key_id=k["AccessKeyId"], aws_secret_access_key=k["SecretAccessKey"], **cfg)
    return boto3.Session(profile_name=C.AWS_PROFILE).client("s3", **cfg)


def signed(key, secs=900):
    try:
        return _s3().generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=secs)
    except Exception:  # noqa: BLE001
        return ""


def explain_pg(k):
    """EXPLAIN VIRTUAL: the statement each virtual schema would send. Shown so engineers see real pushdown, not a claim."""
    sql = {"who": Q_WHO, "allergy": Q_ALLERGY_NOTE, "chain": Q_CHAIN, "readmit": Q_READM_LIVE}[k]
    res = db.run("laptop", "EXPLAIN VIRTUAL " + sql, key=f"explain_{k}")
    out = []
    for r in res["rows"]:
        txt = str(list(r.values())[1])
        if "FROM JDBC" in txt and "STATEMENT '" in txt:
            out.append(txt.split("STATEMENT '", 1)[1].rstrip("'").replace("''", "'"))
    return "\n\n".join(dict.fromkeys(out))[:3000] or "(no Postgres statement for this question)"


# ------------------------------------------------------------------ the diagram
def diagram(active):
    """User -> Exasol (semantic views, patient index, note vectors) -> connectors -> Postgres, MongoDB, S3."""
    q = QUESTIONS.get(active)
    on_n, on_e = (set(q["nodes"]) | {"user", "vs"}, set(q["edges"]) | {"U", "V"}) if q else (set(), set())

    def cn(k, extra=""):
        return "node" + extra + ((" on" if k in on_n else " dim") if q else "")

    def ce(k):
        return "edge" + ((" on" if k in on_e else " dim") if q else "")

    def pill(k, x, y):
        c = "pill" + ((" on" if k in on_e else " dim") if q else "")
        return (f'<g class="{c}"><rect x="{x - 16}" y="{y - 15}" width="32" height="30" rx="15"/>'
                f'<text x="{x}" y="{y + 5}" text-anchor="middle">{SHOWN[k]}</text></g>')

    lbl = ""
    if q and q.get("go"):
        for e, x in (("P", 110), ("M", 310), ("S", 510)):
            if e in on_e:
                bx, anc = (x - 22, "end") if e == "S" else (x + 22, "start")
                lbl += (f'<text class="flowlbl" x="{x - 22}" y="452" text-anchor="end">&darr; {q["go"]}</text>'
                        f'<text class="flowlbl back" x="{bx}" y="474" text-anchor="{anc}">&uarr; {q["back"]}</text>')
    mpi_cls = "udf" + ((" on" if "mpi" in on_n else " dim") if q else "")
    vec_cls = "udf" + ((" on" if "vec" in on_n else " dim") if q else "")
    return f'''<div class="dgm"><svg viewBox="0 0 620 630" role="img" aria-label="Architecture: one Exasol endpoint over a Postgres legacy HIS, a MongoDB EHR and a DICOM archive on S3">
  <line class="{ce("U")}" x1="310" y1="72" x2="310" y2="112"/>
  <line class="{ce("V")}" x1="310" y1="338" x2="310" y2="364"/>
  <line class="{ce("P")}" x1="110" y1="420" x2="110" y2="500"/>
  <line class="{ce("M")}" x1="310" y1="420" x2="310" y2="500"/>
  <line class="{ce("S")}" x1="510" y1="420" x2="510" y2="500"/>
  <g class="{cn("user", " user")}"><rect x="160" y="14" width="300" height="58" rx="29"/><text class="nt" x="310" y="40" text-anchor="middle">Clinician · analyst · AI agent</text><text class="ns" x="310" y="60" text-anchor="middle">any SQL tool, dashboard or MCP client</text></g>
  <g class="{cn("exa", " exa")}"><rect x="40" y="112" width="540" height="226" rx="18"/><text class="nt" x="62" y="144">Exasol</text><text class="ns" x="138" y="144">one governed SQL endpoint for the whole chain</text></g>
  <text x="310" y="331" text-anchor="middle" style="font-size:11px;font-weight:700;fill:#12796A;letter-spacing:.02em">row filter per person · PHI masking · audit log</text>
  <g class="sem"><rect x="62" y="158" width="496" height="70" rx="12"/><text class="st1" x="82" y="186">Semantic views · the certified definitions</text><text class="st2" x="82" y="208">one patient, one readmission rule, one safety check, for every branch</text></g>
  <g class="{mpi_cls}"><rect x="62" y="240" width="240" height="80" rx="12"/><text class="ut" x="80" y="268">Patient index</text><text class="us" x="80" y="288">1,609 records &rarr; 1,224 people</text><text class="us" x="80" y="306">rules in SQL, every link explained</text></g>
  <g class="{vec_cls}"><rect x="318" y="240" width="240" height="80" rx="12"/><text class="ut" x="336" y="268">Note vectors</text><text class="us" x="336" y="288">3,976 notes &times; 384 dimensions</text><text class="us" x="336" y="306">similarity = join + GROUP BY</text></g>
  <g class="{cn("vs", " vsband")}"><rect x="30" y="364" width="560" height="56" rx="14"/><text class="vt" x="310" y="388" text-anchor="middle">Virtual schemas &amp; connectors</text><text class="vs2" x="310" y="407" text-anchor="middle">each system is queried where it is, read-only; only answers come back</text></g>
  <g class="{cn("pg")}"><rect x="20" y="500" width="180" height="110" rx="16"/><text class="nt" x="38" y="536">Legacy HIS</text><text class="ns" x="38" y="559">Postgres · Branch A,</text><text class="ns" x="38" y="579">Branch C before 2024</text></g>
  <g class="{cn("mongo")}"><rect x="220" y="500" width="180" height="110" rx="16"/><text class="nt" x="238" y="536">Modern EHR</text><text class="ns" x="238" y="559">MongoDB · Branch B,</text><text class="ns" x="238" y="579">Branch C since 2024</text></g>
  <g class="{cn("s3")}"><rect x="420" y="500" width="180" height="110" rx="16"/><text class="nt" x="438" y="536">PACS</text><text class="ns" x="438" y="559">DICOM on Amazon S3</text><text class="ns" x="438" y="579">X-ray · CT · MRI</text></g>
  {pill("P", 110, 460)}{pill("M", 310, 460)}{pill("S", 510, 460)}
  {lbl}
</svg></div>'''


SHOWN = {"P": "A", "M": "B", "S": "C"}
LEGEND = {"P": "Legacy HIS (hospital information system): the official PostgreSQL virtual schema (JDBC) pushes each query down to the 2009-era database, read-only",
          "M": "Modern EHR (electronic health record): the MongoDB virtual schema turns nested documents (allergies, medications, observations) into related SQL tables",
          "S": "PACS (picture archiving and communication system) on S3: Exasol reads the DICOM header index in place; the images stay as files"}


# ------------------------------------------------------------------ answer visuals
def big3(items):
    return '<div class="big3">' + "".join(
        f'<div class="b3{" hl" if hl else ""}"><div class="v">{v}</div><div class="k">{k}</div></div>' for v, k, hl in items) + "</div>"


def esc(v):
    return _h.escape("" if v is None else str(v))


def answer(k, out):
    res = out["main"]
    rows = res["rows"]
    if k == "who":
        systems = {r["SOURCE_LABEL"] for r in rows}
        ids = {r["RECORD_ID"] for r in rows}
        score = max((r.get("LINK_SCORE") or 0) for r in rows) if rows else 0
        nums = [(f"{len(systems)}", "systems hold her data, none shares an ID", False),
                (f"{len(ids)} &rarr; 1", "record and image IDs resolved to one person", True),
                (f"{res['secs']:.1f} s", "live, end to end", False)]
        cls = {"Legacy HIS": "legacy", "Modern EHR": "modern", "PACS on S3": "pacs"}
        vis = ""
        for r in rows:
            why = (f'<div class="why">linked, score {int(r["LINK_SCORE"])}: {esc(r["MATCH_REASON"])}</div>' if r.get("LINK_SCORE")
                   else f'<div class="why">{esc(r["MATCH_REASON"])}</div>' if r["SOURCE_LABEL"] == "PACS on S3"
                   else '<div class="why">anchor record (the modern EHR)</div>')
            mob = f' &middot; mobile <b>{esc(r["MOBILE"])}</b>' if r.get("MOBILE") else ""
            vis += (f'<div class="rec"><div class="sys {cls[r["SOURCE_LABEL"]]}">{esc(r["SOURCE_LABEL"])}<br>{esc(r["BRANCH"])}</div><div>'
                    f'<div class="id">{esc(r["RECORD_ID"])}</div>'
                    f'<div class="as">name <b>{esc(r["NAME_AS_RECORDED"])}</b> &middot; born <b>{esc(r["BIRTH_DATE_AS_RECORDED"])}</b>{mob}</div>{why}</div></div>')
        if score:
            vis += '<div class="hint" style="margin-top:.4rem;font-size:.82rem">Same person, three spellings of her name and three formats for one birth date. The DICOM tag carries the legacy ID with the slashes removed.</div>'
    elif k == "allergy":
        ehr = (out["ehr"]["rows"] or [{}])[0].get("ALLERGIES_RECORDED")
        note = (out["note"]["rows"] or [{}])[0]
        a = rows[0] if rows else {}
        nums = [("1", "conflict found for her", True),
                (f"{int(ehr or 0)}", "allergies on file in the Branch B EHR", False),
                (f"{res['secs']:.1f} s", "live, end to end", False)]
        if a:
            vis = (f'<div class="alert"><div class="h">Stop: {esc(a["DRUG"])} is a {esc(a["DRUG_CLASS"]).lower()}</div>'
                   f'<div class="d">Recorded in Branch A: <b>{esc(a["ALLERGY_AS_RECORDED"])}</b> ({esc(a["SEVERITY"])})</div>'
                   f'<div class="src">Order {esc(a["ORDER_STATUS"])} in the {"Branch B EHR" if a["PRESCRIBED_IN"] == "MODERN_EHR" else "legacy HIS"} under {esc(a["PRESCRIBED_UNDER"])} '
                   f'&middot; allergy in the {"legacy HIS" if a["ALLERGY_RECORDED_IN"] == "LEGACY_HIS" else "EHR"} under {esc(a["ALLERGY_RECORD_ID"])}</div></div>'
                   f'<div class="vs2c"><div class="c"><div class="k">What Branch B sees</div><div class="v">{esc(a["DRUG"])} {esc(a["DOSE"])}</div>'
                   f'<div class="s">draft order &middot; no known drug allergies at this site</div></div><div class="x">&times;</div>'
                   f'<div class="c bad"><div class="k">What Branch A knew in 2019</div><div class="v">Penicillin: anaphylaxis</div>'
                   f'<div class="s">free text in a 2009-era HIS, never migrated</div></div></div>')
            if note.get("SUMM_TXT"):
                vis += f'<div class="quote">Discharge summary {esc(note["VISIT_NO"])}, {esc(note["ADM_DT"])}: &ldquo;&hellip;{esc(note["SUMM_TXT"][160:420])}&hellip;&rdquo;</div>'
        else:
            vis = '<div class="hint">No conflict found.</div>'
    elif k == "scans":
        tot = out["all"]["rows"]
        n = sum(int(r["STUDIES"]) for r in tot)
        mb = sum(float(r["BYTES"] or 0) for r in tot) / 1e6
        nums = [(f"{n}", f"studies in the PACS ({mb:,.0f} MB of DICOM)", False), (f"{len(rows)}", "are hers, under two different patient IDs", True),
                ("0", "pixels passed through the database", False)]
        cards = ""
        for r in rows:
            img, dcm = signed(r["THUMB_KEY"]), signed(r["S3_KEY"])
            cards += (f'<div class="scan"><img src="{img}" alt="{esc(r["STUDY_DESCRIPTION"])}"/><div class="cap"><b>{esc(r["STUDY_DATE"])} &middot; {esc(r["STUDY_DESCRIPTION"])}</b>'
                      f'<div>{esc(r["INSTITUTION"])} &middot; PatientID tag <code>{esc(r["PACS_PATIENT_ID"])}</code></div>'
                      f'<div class="m">s3://&hellip;/{esc(r["S3_KEY"][:46])}&hellip;</div>'
                      f'<a href="{dcm}" target="_blank">Download the DICOM file &rarr;</a></div></div>')
        vis = f'<div class="scans">{cards}</div>'
        vis += ('<div class="hint" style="font-size:.8rem">Real de-identified images from The Cancer Imaging Archive (COVID-19-AR, CC BY 4.0), '
                'relabelled to the synthetic patient. Today\'s X-ray is acquired and not yet reported.</div>')
    elif k == "similar":
        ls = [float(r["LENGTH_OF_STAY"] or 0) for r in rows]
        ra = sum(1 for r in rows if str(r["READMITTED_30D"]).lower() == "true")
        nums = [("3,976", "clinical notes compared by meaning", False),
                (f"{len(rows)}", "similar diabetic patients over 60, penicillin-allergic", True),
                (f"{res['secs']:.1f} s", "live, end to end", False)]
        vis = "".join(
            f'<div class="sim"><div><div class="nm">Patient {esc(r["UNIFIED_ID"])} &middot; {int(r["AGE"])} y &middot; {esc(r["BRANCH"])}'
            f'<span class="tag {"r" if str(r["READMITTED_30D"]).lower() == "true" else "g"}">{"readmitted &le;30 d" if str(r["READMITTED_30D"]).lower() == "true" else "no readmission"}</span></div>'
            f'<div class="mt">{esc(r["DIAGNOSIS"])} &middot; {esc(r["ADMIT_DATE"])} &middot; {"legacy HIS" if r["SOURCE_SYSTEM"] == "LEGACY_HIS" else "modern EHR"} &middot; similarity {float(r["SIMILARITY"]):.3f}</div></div>'
            f'<div class="ab">{esc(r["ANTIBIOTIC"] or "–")}</div><div class="ls">{int(float(r["LENGTH_OF_STAY"] or 0))} d<span>stay</span></div></div>' for r in rows)
        if rows:
            vis += (f'<div class="hint" style="margin-top:.5rem;font-size:.82rem">None of them received a penicillin. Average stay {sum(ls) / len(ls):.1f} days; '
                    f'{ra} of {len(rows)} came back within 30 days. Synthetic data: this shows the query, not clinical guidance.</div>')
        if out.get("text"):
            vis = f'<div class="hint" style="margin-bottom:.4rem">Searched for: &ldquo;{esc(out["text"])}&rdquo;</div>' + vis
    elif k == "readmit":
        fast = out["fast"]
        tot = sum(int(r["READMISSIONS"]) for r in rows) or 1
        hid = sum(int(r["HIDDEN"]) for r in rows)
        same = [(r["BRANCH"], int(r["READMISSIONS"]), int(r["HIDDEN"])) for r in rows] == \
               [(r["BRANCH"], int(r["READMISSIONS"]), int(r["HIDDEN"])) for r in fast["rows"]]
        nums = [(f"{hid} of {tot}", "readmissions no single branch system can count", True),
                (f"{res['secs']:.2f} s &rarr; {fast['secs']:.2f} s", "live across both systems, then on the Exasol copy", False),
                ("identical" if same else "check", "answer, branch by branch" if same else "compare the two runs", False)]
        top = max(int(r["READMISSIONS"]) for r in rows) if rows else 1
        names = {"BRA": "Branch A", "BRB": "Branch B", "BRC": "Branch C"}
        vis = ('<div class="leg"><span><i style="background:#1FA08B"></i>a branch system sees these</span>'
               '<span><i style="background:#C8102E"></i>only the fused record sees these</span></div>')
        for r in rows:
            n, h = int(r["READMISSIONS"]), int(r["HIDDEN"])
            vis += (f'<div class="rb"><div class="l">{names.get(r["BRANCH"], r["BRANCH"])}<span>{h} of {n} hidden</span></div>'
                    f'<div class="t"><div class="v1" style="width:{100 * (n - h) / top:.1f}%"></div><div class="v2" style="width:{100 * h / top:.1f}%"></div></div>'
                    f'<div class="n">{n}</div></div>')
    else:
        inbed = (out["inbed"]["rows"] or [{}])[0].get("PATIENTS") or 0
        hidden = sum(1 for r in rows if str(r["KNOWN_WHERE_PRESCRIBED"]).lower() == "false")
        nums = [(f"{int(inbed)}", "patients in a bed right now (modern EHR)", False),
                (f"{len(rows)}", "have an order that contradicts a recorded allergy", True),
                (f"{hidden}", "of them: the allergy is missing from the system that wrote the order", False)]
        vis = "".join(
            f'<div class="cu"><div><div class="nm">{esc(r["PATIENT_NAME"])} &middot; {int(r["AGE"])} y &middot; {esc(r["ENCOUNTER_ID"])}</div>'
            f'<div class="mt" style="font-style:normal">{esc(r["DRUG"])} ({esc(r["ORDER_STATUS"])}) &times; &ldquo;{esc(r["ALLERGY_AS_RECORDED"])}&rdquo; '
            f'in the {"legacy HIS" if r["ALLERGY_RECORDED_IN"] == "LEGACY_HIS" else "EHR"}'
            + (' &middot; <b style="color:#C8102E">no allergy on file in the system that wrote the order</b>' if str(r["KNOWN_WHERE_PRESCRIBED"]).lower() == "false" else ' &middot; <b style="color:#12796A">allergy on file where prescribed</b>') + '</div></div></div>'
for r in rows)
    return nums, vis


# ------------------------------------------------------------------ page
@st.cache_data(ttl=20, show_spinner=False)
def health():
    h = {}
    for k, sql in (("exa", "SELECT 1"), ("pg", "SELECT COUNT(*) FROM HOSP_LEGACY.PAT_MSTR WHERE PAT_NO = 'BRA/2014/000731'"),
                   ("mongo", f"SELECT COUNT(*) FROM HOSP_SRC.MODERN_PATIENTS WHERE RECORD_ID = '{HERO_EHR}' GROUP BY RECORD_ID"),
                   ("s3", "SELECT COUNT(*) FROM HOSP_SRC.IMAGING_INDEX GROUP BY MODALITY")):
        h[k] = bool(db.run("laptop", sql)["live"])
    return h


h = health()
pill = lambda ok, t: f'<span class="hs-pill{"" if ok else " down"}">{t}</span>'  # noqa: E731
html(f'<div class="pagehead">{_logo()}<span class="ph-t">Hospital chain &middot; one patient, every branch &middot; live demo</span></div>')
html(f'''<div class="hero-slim"><div class="hs-t">Every branch's record of a patient, <em>in one query</em>
  <span>An old hospital information system, a modern electronic health record and an imaging archive, answered by one Exasol endpoint. Nothing migrated first.</span></div>
  <div class="hs-m">{pill(h["exa"], "Exasol")}{pill(h["pg"], "Legacy HIS")}{pill(h["mongo"], "Modern EHR")}{pill(h["s3"], "PACS on S3")}</div></div>''')

tab_over, tab_demo, tab_agent, tab_flow = st.tabs(["1 · Overview", "2 · Live demo", "3 · Who is asking", "4 · How it works"])

with tab_demo:
    DATA = [("Branch A", "Legacy HIS", "Postgres", "PAT_MSTR 874 · VISIT_HDR 3,365", "<b>Hospital information system</b>: registration, admissions, pharmacy, labs. 2009-era schema: dates as text, surnames as initials, allergies as free text"),
            ("Branch B", "Modern EHR", "MongoDB", "patients 735 · encounters 2,605", "<b>Electronic health record</b>: the clinical record. FHIR-style documents with allergies, medications and vitals nested inside"),
            ("Branch C", "Both", "migrating", "HIS until Mar 2024, EHR since", "the same patients registered twice, once in each system"),
            ("Imaging", "PACS", "Amazon S3", "168 DICOM studies · X-ray, CT, MRI", "<b>Picture archiving and communication system</b>: where the scanners store images (DICOM files); a header index sits beside them"),
            ("Exasol", "Patient index", "+ note vectors", "1,609 records &rarr; 1,224 people", "deterministic matching rules in SQL; 3,976 notes embedded")]
    html('<div class="qk" style="margin-top:.2rem">What data lives where</div><div class="dmap">' + "".join(
        f'<div class="dm{" exa" if k == "Exasol" else ""}"><div class="dk">{k}</div><div class="ds">{sys} <span>{role}</span></div>'
        f'<div class="dt">{tables}</div><div class="dd">{d}</div></div>' for k, sys, role, tables, d in DATA) + "</div>")

    active = ss.get("active")
    left, right = st.columns([1.05, 1], gap="large")

    with right:
        html('<div class="qk">Ask a question</div>')
        with st.container(key="qbtns"):
            for k, q in QUESTIONS.items():
                if st.button(f'{q["n"]}  ·  {q["ask"]}', key=f"q_{k}", use_container_width=True,
                             type="primary" if k == active else "secondary"):
                    ss["active"], ss["pending"] = k, True
                    st.rerun()
        if active == "similar":
            ss["sim_text"] = st.text_input("Or describe a case in your own words (leave empty to use her note from today)",
                                           value=ss.get("sim_text", ""), placeholder="elderly diabetic, fever and cough, crackles at the right base")

        if active and ss.get("pending"):
            with st.spinner(f"Asking: {QUESTIONS[active]['ask']}"):
                ss[f"done_{active}"] = run_question(active)
            ss["pending"] = False
            st.rerun()

        if not active:
            html('<div class="ans"><div class="q">Pick a question</div><div class="hint">Mrs. Meenakshi Sundaram, 68, diabetic, was treated in '
                 'Branch A in 2019. Today she is admitted in Branch B with fever and breathlessness, and a doctor has drafted her first '
                 'prescription. Each question is answered live; the diagram lights up the systems it touches.</div></div>')
        elif ss.get(f"done_{active}"):
            q, out = QUESTIONS[active], ss[f"done_{active}"]
            nums, vis = answer(active, out)
            cached = "" if out["main"]["live"] else f'<div class="cached">Live source unavailable: showing the last good run. ({esc(out["main"].get("error"))[:140]})</div>'
            html(f'''<div class="ans"><div class="q">{q["ask"]}</div><div class="src">{q["src"]}</div>
                 {big3(nums)}{vis}{cached}
                 {(f'<div class="punch"><div class="pt">{q["punch"][0]}</div><div class="pv">{q["punch"][1]}</div>'
                   f'<div class="ps">{q["punch"][2]}</div></div>') if q.get("punch") else ""}
                 <div class="did" style="margin-top:.8rem"><div class="k">What Exasol did</div><ul>{"".join(f"<li>{d}</li>" for d in q["did"])}</ul></div></div>''')
            with st.expander("For engineers: the SQL, and what each source received"):
                sql = {"who": Q_WHO, "allergy": Q_ALLERGY, "scans": Q_SCANS, "similar": out.get("sql", q_similar()),
                       "readmit": Q_READM_LIVE, "chain": Q_CHAIN}[active]
                st.caption("The SQL you write in Exasol")
                st.code(sql.strip()[:6000], language="sql", wrap_lines=True)
                if active in ("who", "allergy", "chain"):
                    st.caption("The patient index behind UNIFIED_ID: deterministic rules in SQL (sql/20_mpi.sql)")
                    st.code((SQLDIR / "20_mpi.sql").read_text().split("-- 2.", 1)[1].split("-- 3.", 1)[0].strip()[:2400], language="sql", wrap_lines=True)
                if active == "allergy":
                    st.caption("The 2019 note, read live from the legacy HIS")
                    st.code(Q_ALLERGY_NOTE, language="sql", wrap_lines=True)
                if active == "scans":
                    st.caption("S3 received: one GET for index/dicom_index.csv, signed with the read-only key. The view behind it:")
                    st.code((SQLDIR / "25_imaging.sql").read_text().split("CREATE OR REPLACE VIEW", 2)[1].join(["CREATE OR REPLACE VIEW", ""]).strip(), language="sql", wrap_lines=True)
                if active == "readmit":
                    st.caption("The same question on the copy inside Exasol")
                    st.code(Q_READM_FAST, language="sql", wrap_lines=True)
                    st.caption("The copy is built once with this statement:")
                    st.code(Q_ACCEL, language="sql", wrap_lines=True)
                    if st.button("Rebuild it now", key="rebuild"):
                        with st.spinner("Copying encounters from Postgres + MongoDB into Exasol…"):
                            r = db.run("laptop", Q_ACCEL, key="accel_build")
                        st.success(f"Copied {r['rows'][0].get('ROWS_WRITTEN', 0):,} encounters in {r['secs']:.1f} s" if r["live"]
                                   else f"Rebuild failed: {r['error']}")
                if active in ("allergy", "chain", "who", "readmit"):
                    st.caption("What Postgres received (pushed down by the virtual schema)")
                    st.code(explain_pg(active), language="sql", wrap_lines=True)

    with left:
        html(diagram(active))
        q = QUESTIONS.get(active)
        edges = sorted(q["edges"] if q else LEGEND, key=lambda e: SHOWN[e])
        html("".join(f'<div class="hint" style="margin-top:.4rem"><b>{SHOWN[e]}</b> &middot; {LEGEND[e]}</div>' for e in edges))

# ------------------------------------------------------------------ tab 1: overview
Q_MPI_STATS = """SELECT SOURCE_SYSTEM, COUNT(*) AS RECORDS, COUNT(DISTINCT UNIFIED_ID) AS PEOPLE FROM HOSP_CORE.MPI GROUP BY SOURCE_SYSTEM"""
Q_MPI_TOTAL = """SELECT 'all' AS K, COUNT(*) AS RECORDS, COUNT(DISTINCT UNIFIED_ID) AS PEOPLE,
       (SELECT COUNT(*) FROM HOSP_CORE.MATCH_REVIEW_QUEUE) AS REVIEW FROM HOSP_CORE.MPI GROUP BY 'all'"""


@st.cache_data(ttl=600, show_spinner=False)
def overview_query(sql, key):
    return db.run("laptop", sql, key=key)


with tab_over:
    html('''<div class="ov-band"><div class="ov-k">From federation to data fusion</div>
      <div class="ov-h">Hospitals are distributed. Patients are not.</div>
      <div class="ov-s">A chain grows by acquisition: every branch arrives with its own system, its own IDs and its own spelling of the same person.
      Start live with federation, resolve identity once, certify the definitions, then accelerate only what proves worth it.</div></div>''')
    html('''<div class="fail3">
      <div class="f3"><div class="f3-k">Breaks down</div><div class="f3-t">Migrate every branch first</div><div class="f3-d">Years before the first answer</div></div>
      <div class="f3"><div class="f3-k">Breaks down</div><div class="f3-t">Phone and fax between branches</div><div class="f3-d">The record arrives after the prescription</div></div>
      <div class="f3"><div class="f3-k">Breaks down</div><div class="f3-t">Copy everything to a lake</div><div class="f3-d">One more pipeline, PHI in one more place</div></div>
      <div class="f3-ar">&rarr;</div>
      <div class="f3 good"><div class="f3-k">With Exasol</div><div class="f3-t">One patient, live</div><div class="f3-d">Federate &middot; resolve identity &middot; certify meaning</div></div></div>''')
    html('''<div class="dmap" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-top:.8rem">
      <div class="dm"><div class="dk">HIS</div><div class="ds">Hospital information system <span>the older system</span></div>
        <div class="dd">Runs the hospital: registration, admissions and discharges, billing, pharmacy orders, lab results. Here: Branch A, on Postgres.</div></div>
      <div class="dm"><div class="dk">EHR</div><div class="ds">Electronic health record <span>the newer system</span></div>
        <div class="dd">The clinical record of the patient: problems, allergies, medications, vitals, notes. Here: Branch B, on MongoDB.</div></div>
      <div class="dm"><div class="dk">PACS</div><div class="ds">Picture archiving and communication system</div>
        <div class="dd">Where the X-ray, CT and MRI scanners store images, as DICOM files with a header (patient ID, date, body part). Here: Amazon S3.</div></div></div>''')

    c1, c2 = st.columns([1, 1.1], gap="large")
    with c1:
        html('<div class="ov-band"><div class="ov-k">How it connects</div><div class="ov-h">One path for every question</div></div>')
        html(diagram(None))
    with c2:
        html('''<div class="ov-band"><div class="ov-k">Reading the diagram</div><div class="ov-h">Identity first, then meaning, then execution</div></div>
          <div class="layers">
          <div class="ly"><div class="ly-n">People</div><div class="ly-t">Clinicians, analysts and their AI agents: one endpoint, any tool</div></div>
          <div class="ly dark"><div class="ly-n">Semantic views</div><div class="ly-t">One definition of a patient, a readmission and a drug conflict for every branch</div></div>
          <div class="ly exa"><div class="ly-n">Patient index</div><div class="ly-t">Which records are the same person, with the reason for every link</div></div>
          <div class="ly exa"><div class="ly-n">Virtual schemas</div><div class="ly-t">Each branch system queried where it is, read-only</div></div>
          <div class="ly"><div class="ly-n">Branch systems</div><div class="ly-t">Stay where they are, owned by their teams, migrated when it suits</div></div></div>''')

    # ---- identity: measured against the generator's ground truth
    tot = (overview_query(Q_MPI_TOTAL, "mpi_total")["rows"] or [{}])[0]
    qf = HERE / "cache" / "mpi_quality.json"
    qual = json.loads(qf.read_text()) if qf.exists() else {}
    if tot:
        html(f'''<div class="ov-band"><div class="ov-k">Why a patient index</div>
          <div class="ov-h">{int(tot["RECORDS"]):,} records, {int(tot["PEOPLE"]):,} people</div>
          <div class="ov-s">The same person registered at several branches, with initials for surnames, day and month swapped, landlines
          instead of mobiles. Deterministic rules in SQL link them; borderline pairs go to a person, never to a guess.</div></div>
          <div class="tok"><div class="tk2"><div class="v">{int(tot["RECORDS"]):,}</div><div class="k">patient records across the legacy HIS and the modern EHR</div></div>
          <div class="tka">&rarr;</div><div class="tk2 good"><div class="v">{int(tot["PEOPLE"]):,}</div><div class="k">people, one UNIFIED_ID each</div></div>
          <div class="tka">&middot;</div><div class="tk2 navy"><div class="v">{qual.get("precision_pct", "–")}% &middot; {qual.get("recall_pct", "–")}%</div>
          <div class="k">links correct &middot; true links found (measured against the generator's ground truth; {int(tot["REVIEW"]):,} pairs queued for review)</div></div></div>''')

    # ---- wrong but plausible: readmissions counted per branch system
    rd = overview_query(Q_READM_FAST, "ov_readm")
    if rd["rows"]:
        allr = sum(int(r["READMISSIONS"]) for r in rd["rows"])
        vis = allr - sum(int(r["HIDDEN"]) for r in rd["rows"])
        html(f'''<div class="ov-band"><div class="ov-k">Why a certified definition</div>
          <div class="ov-h">Wrong but plausible is worse than an error</div>
          <div class="ov-s">"30-day readmissions across the chain", measured on this demo's data, two ways.</div></div>
          <div class="fan">
            <div class="fn-row"><div class="fn-l">Each branch system counts its own<span>the SQL runs fine</span></div>
              <div class="fn-tr"><div class="fn-f bad" style="width:{100 * vis / allr:.1f}%"><span>{vis}</span></div></div></div>
            <div class="fn-row"><div class="fn-l">Certified definition<span>same person, any branch</span></div>
              <div class="fn-tr"><div class="fn-f good" style="width:100%"><span>{allr}</span></div></div></div>
            <div class="fn-foot"><span class="fn-x">{100 * (allr - vis) / allr:.0f}% under-counted</span>
              {allr - vis} readmissions cross a branch or a system, so no single system can see them.
              <b>HOSP_GOV.READMISSIONS_30D carries the one definition every tool uses.</b></div></div>''')

    html('''<div class="ov-band"><div class="ov-k">The adoption path</div><div class="ov-h">Federate first. Accelerate what earns it.</div></div>
      <div class="path5">
        <div class="p5 done"><div class="p5-n">1</div><div class="p5-t">Attach</div><div class="p5-d">each branch system, read-only</div><div class="p5-s">in this demo</div></div>
        <div class="p5 done"><div class="p5-n">2</div><div class="p5-t">Resolve</div><div class="p5-d">one patient, every record</div><div class="p5-s">in this demo</div></div>
        <div class="p5 sv"><div class="p5-n">3</div><div class="p5-t">Certify</div><div class="p5-d">definitions, access, masking</div><div class="p5-s">semantic views</div></div>
        <div class="p5 done"><div class="p5-n">4</div><div class="p5-t">Accelerate</div><div class="p5-d">copy the hot paths</div><div class="p5-s">in this demo</div></div>
        <div class="p5"><div class="p5-n">5</div><div class="p5-t">Agent-enable</div><div class="p5-d">MCP, per-person rights</div><div class="p5-s">tab 3</div></div></div>''')
    html('<div class="footnote">Data: patients, encounters and notes are synthetic (generated, seeded). Images are real, de-identified studies from '
         'The Cancer Imaging Archive (COVID-19-AR and UPENN-GBM, CC BY 4.0), relabelled to synthetic patients. No real hospital systems are involved.</div>')


# ------------------------------------------------------------------ tab 3: the same question, asked by two people through MCP
import agent_tab as ag  # noqa: E402

with tab_agent:
    html(ag.CSS)
    html('<div class="sec-h"><div class="k">Agents ask the questions now</div>'
         '<div class="t" style="font-weight:800;font-size:1.35rem">Whose identity reaches the data? Which definition does the query use? Can the answer be replayed?</div></div>')
    pick = st.radio("Who is asking?", list(ag.PEOPLE), horizontal=True, key="ag_user",
                    format_func=lambda u: f"{ag.PEOPLE[u][0]} ({ag.PEOPLE[u][1]})")
    html(f'<div class="ag-who">Question from <b>{ag.PEOPLE[pick][0]}</b>: &ldquo;{ag.QUESTION}&rdquo;'
         f'<div class="u">The AI client connects through the Exasol MCP server as database user {pick}</div></div>')
    done = ss.get(f"ag_{pick}")
    html(ag.flow(pick, bool(done)))
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Ask through the Exasol MCP server", key="ag_ask", type="primary", use_container_width=True):
            with st.spinner(f"Asking as {pick}…"):
                ss[f"ag_{pick}"] = ag.ask_or_cached(pick)
            st.rerun()
    with c2:
        if st.button("Now try to read the raw identities", key="ag_bypass", use_container_width=True):
            with st.spinner("Asking for the table behind the views…"):
                try:
                    ss[f"ag_no_{pick}"] = ag.bypass(pick)
                except Exception as e:  # noqa: BLE001
                    ss[f"ag_no_{pick}"] = {"error": True, "text": str(e)[:200], "secs": 0}
            st.rerun()

    if done:
        if not done.get("live"):
            html(f'<div class="cached">Live source unavailable: showing the last good run. ({esc(done.get("error", ""))[:120]})</div>')
        left_a, right_a = st.columns([1, 1.15], gap="large")
        with left_a:
            html('<div class="qk">What the agent did, step by step</div>' + ag.steps_html(done))
        with right_a:
            html(f'<div class="ans"><div class="q">{ag.QUESTION}</div><div class="src">Answered as {pick} through the Exasol MCP server, '
                 f'{done.get("secs", 0):.1f} s end to end, of which {sum(x.get("secs", 0) for x in done.get("steps", [])):.1f} s in the database '
                 f'(the rest is starting the MCP server)</div>{ag.answer_html(done, big3)}</div>')
        with st.expander("The SQL that produced this answer (replay it next week, same person, same rules)"):
            st.code(ag.SQL_TOP, language="sql")

    a, b = ss.get("ag_HOSP_DR_BRB"), ss.get("ag_HOSP_QUALITY_ANALYST")
    if a and b:
        def _n(o):
            t = o.get("top") or []
            return int((t[0] if t else {}).get("ALERTS") or 0), sum(1 for r in t if str(r.get("PATIENT_NAME", "")).startswith("Patient "))
        (na, ma), (nb, mb) = _n(a), _n(b)
        html('<div class="qk" style="margin-top:.8rem">Same question, same SQL, two people</div><div class="ag-cmp">'
             f'<div class="c"><div class="l">{ag.PEOPLE["HOSP_DR_BRB"][0]}</div><div class="v">{na} alerts &middot; names shown</div><div class="l">patients registered in Branch B, with their full history from every branch</div></div>'
             f'<div class="c"><div class="l">{ag.PEOPLE["HOSP_QUALITY_ANALYST"][0]}</div><div class="v">{nb} alerts &middot; {mb} pseudonyms</div><div class="l">every branch, no identities</div></div></div>'
             '<div class="hint">The rule lives in the engine, so every assistant inherits it. Nobody re-implements it per tool.</div>')

    no = ss.get(f"ag_no_{pick}")
    if no:
        msg = no.get("text", "")
        if "privilege" in msg.lower():
            msg = msg.split("rejected the query:")[-1].split("(Session")[0].strip() if "rejected" in msg else msg
            html(f'<div class="ag-no"><b>Refused by Exasol.</b> {esc(ag.SQL_BYPASS.split("--")[0].strip())} &rarr; {esc(msg)}. '
                 'The rule is in the database, not in the prompt.</div>')
        else:
            html('<div class="cached">Could not reach the database just now, so this is not a refusal. Check <code>exakit status</code>, then click again.</div>')

    html('<div class="qk" style="margin-top:1rem">Every call is on record</div>')
    if st.button("Show the audit log", key="ag_audit"):
        ss["ag_audit_res"] = db.run("laptop", ag.SQL_AUDIT, key="agent_audit")
    aud = ss.get("ag_audit_res")
    if aud:
        rows = "".join(f'<tr><td><b>{esc(r["USER_NAME"])}</b></td><td>{esc(str(r["START_TIME"])[:19])}</td>'
                       f'<td class="{"ok" if str(r["SUCCESS"]).lower() in ("true", "1") else "f"}">{"ran" if str(r["SUCCESS"]).lower() in ("true", "1") else "REFUSED"}</td>'
                       f'<td>{r["SECS"]}</td><td><code>{esc(r["SQL_TEXT"])}</code></td></tr>' for r in aud["rows"])
        html(f'<div class="ag-aud"><table><tr><th>Who</th><th>When</th><th></th><th>Seconds</th><th>SQL</th></tr>{rows}</table></div>'
             + ("" if aud.get("live") else '<div class="cached">Live source unavailable: showing the last good run.</div>'))
    html('<div class="footnote">Real Exasol MCP server, real database users, row filter and masking in the engine. The SQL is the one an AI client writes '
         'after reading the view definitions (fixed here; in Claude Desktop the model writes it live). Synthetic patients; no real hospital systems.</div>')


# ------------------------------------------------------------------ tab 4: how it works (flow diagram + one question traced)
import flow  # noqa: E402

Q_FLOW_COUNTS = """SELECT
  (SELECT COUNT(*) FROM HOSP_CORE.PATIENT_RECORDS WHERE SOURCE_SYSTEM = 'LEGACY_HIS') AS LEGACY,
  (SELECT COUNT(*) FROM HOSP_CORE.PATIENT_RECORDS WHERE SOURCE_SYSTEM = 'MODERN_EHR') AS MODERN,
  (SELECT COUNT(*) FROM HOSP_CORE.MPI) AS RECORDS,
  (SELECT COUNT(DISTINCT UNIFIED_ID) FROM HOSP_CORE.MPI) AS PEOPLE,
  (SELECT COUNT(*) FROM HOSP_CORE.MATCH_REVIEW_QUEUE) AS REVIEW,
  (SELECT COUNT(*) FROM HOSP_CORE.NOTE_INDEX) AS NOTES,
  (SELECT COUNT(*) FROM HOSP_CORE.NOTE_VECTORS) AS VECTORS
FROM DUAL"""

with tab_flow:
    html(flow.CSS)
    html('<div class="ov-band"><div class="ov-k">How it works</div>'
         '<div class="ov-h">Everything expensive happens once. A question only reads.</div>'
         '<div class="ov-s">The top band is prepared ahead of time and refreshed nightly. The bottom band is the whole path of a question: '
         'from a person or an agent, through the rules, to the three branch systems and back. The numbers in the boxes are read live.</div></div>')
    c = (overview_query(Q_FLOW_COUNTS, "flow_counts")["rows"] or [{}])[0]
    s3n = overview_query(Q_SCANS_ALL, "flow_s3")["rows"]
    counts = {"legacy": int(c.get("LEGACY") or 0), "modern": int(c.get("MODERN") or 0), "records": int(c.get("RECORDS") or 0),
              "people": int(c.get("PEOPLE") or 0), "review": int(c.get("REVIEW") or 0), "notes": int(c.get("NOTES") or 0),
              "vectors": int(c.get("VECTORS") or 0), "studies": sum(int(r["STUDIES"]) for r in s3n),
              "mb": sum(float(r["BYTES"] or 0) for r in s3n) / 1e6}
    html(flow.setup_band(counts))
    html(flow.query_band())

    html('<div class="ov-band"><div class="ov-k">Follow one question</div>'
         '<div class="ov-h">&ldquo;Is the prescription Branch B just drafted safe for her?&rdquo;</div>'
         '<div class="ov-s">The same question taken apart: each step run on its own against the system that holds the data, then all of it '
         'as the one certified view the live demo uses. Times are measured now.</div></div>')
    if st.button("Run the trace, step by step", key="flow_trace", type="primary"):
        sqls = flow.trace_sql(HERO_EHR, "BRA/2014/000731")
        ss["flow_res"] = {k: db.run("laptop", q, key=f"flow_{k}") for k, q in sqls.items()}
    res = ss.get("flow_res")
    if res:
        html(flow.trace_html(res))
        if not all(r["live"] for r in res.values()):
            html('<div class="cached">A source was unavailable: some steps show the last good run.</div>')
        with st.expander("For engineers: the five statements"):
            for k, q in flow.trace_sql(HERO_EHR, "BRA/2014/000731").items():
                st.code(q, language="sql", wrap_lines=True)
