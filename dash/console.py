"""Hospital-chain console: everything that is not Dash wiring. Ported from the Streamlit console (../app/app.py).

The SQL lives in QUERIES; build.py writes each entry to queries/business/<name>.sql (and EXPLAIN VIRTUAL variants to
explain/<name>.sql, outside queries/ so dash-server's smoke test, which wraps every query in SELECT * FROM (...), skips
them). At run time every statement goes through dash-server's Exasol profile: the kit's read-only user, never admin.
Every successful result is cached in <repo>/dash/cache, so a source that fails on stage shows the last
good run, labelled.
"""
import html as _h
import json
import re
import time
from pathlib import Path

import site_config as S  # noqa: E402  repository path, bucket, key (frozen into the deployed copy)
import embed  # top level: dash-server only resolves sibling modules while app.py is being imported

HOME = Path(S.ROOT)
CACHE = HOME / "dash" / "cache"            # outside the dash-server artifact, so it survives a redeploy
SQLDIR = HOME / "sql"
BUCKET, REGION = S.BUCKET, S.REGION
HERO_EHR, HERO_LEGACY, HERO_NOTE = "BRB-P-108842", "BRA/2014/000731", "M:ENC-BRB-2610-02605"

# The chain is fictional. The data uses the codes BRA/BRB/BRC (inside record IDs too); on screen a bare code reads as
# "Branch A/B/C". generic() is applied to every fragment the page renders.
BRANCHES = {"BRA": ("Branch A", "Branch A"), "BRB": ("Branch B", "Branch B"), "BRC": ("Branch C", "Branch C")}
_CITY = re.compile(r"\b(" + "|".join(c for c, _ in BRANCHES.values()) + r")\b")
_CODE = re.compile(r"(?<![\w/-])(" + "|".join(BRANCHES) + r")(?![\w/-])")
_BY_CITY = {c: g for c, g in BRANCHES.values()}
_LETTER = re.compile(r"\bBranch ([ABC])\b")  # older wording still in some fragments
_BY_LETTER = dict(zip("ABC", (g for _, g in BRANCHES.values())))


def generic(text):
    """City names and bare branch codes -> generic branch names. Record IDs such as BRA/2014/000731 are left alone."""
    text = _CITY.sub(lambda m: _BY_CITY[m.group(1)], str(text))
    text = _LETTER.sub(lambda m: _BY_LETTER[m.group(1)], text)
    return _CODE.sub(lambda m: BRANCHES[m.group(1)][1], text)

# ------------------------------------------------------------------ SQL
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

SIM_TAIL = f"""
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
JOIN   pen ON pen.UNIFIED_ID = c.UNIFIED_ID                                     -- penicillin allergy, recorded in either system
LEFT JOIN abx a ON a.ENCOUNTER_ID = c.ENCOUNTER_ID
LEFT JOIN readm r ON r.PREV_ENCOUNTER_ID = c.ENCOUNTER_ID
WHERE  YEARS_BETWEEN(CURRENT_DATE, p.BIRTH_DATE) >= 60
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.UNIFIED_ID ORDER BY c.SIMILARITY DESC) = 1    -- best match per patient
ORDER  BY c.SIMILARITY DESC
LIMIT  6"""
Q_SIMILAR = (f"WITH q AS (SELECT DIM, VAL FROM HOSP_CORE.NOTE_VECTORS WHERE NOTE_ID = '{HERO_NOTE}'),"
             "   -- her admission note from today" + SIM_TAIL)
# {vec!r}: a VALUES list of 384 numbers this console computes from the typed text (never the text itself)
Q_SIMILAR_TEXT = "WITH q AS ({vec!r}),   -- the typed text, embedded by the same model as the notes" + SIM_TAIL

Q_READM_SHAPE = """SELECT BRANCH, COUNT(*) AS READMISSIONS, SUM(CASE WHEN VISIBLE_TO_ONE_SYSTEM THEN 0 ELSE 1 END) AS HIDDEN
FROM   {src}
GROUP  BY BRANCH ORDER BY BRANCH"""
Q_READM_LIVE = "-- live: Postgres + MongoDB through the patient index, nothing copied\n" + Q_READM_SHAPE.format(src="HOSP_CORE.READMISSIONS_30D")
Q_READM_FAST = "-- on the copy inside Exasol (built once from the same live views)\n" + Q_READM_SHAPE.format(src="HOSP_ACCEL.READMISSIONS_30D")
Q_ACCEL = "CREATE OR REPLACE TABLE " + (SQLDIR / "50_accelerate.sql").read_text().split("CREATE OR REPLACE TABLE", 1)[1].split(";", 1)[0].strip() \
    if (SQLDIR / "50_accelerate.sql").exists() else "-- see sql/50_accelerate.sql"

Q_CHAIN = """-- every patient in a bed RIGHT NOW whose order contradicts an allergy recorded for the same person anywhere
SELECT p.PATIENT_NAME, FLOOR(YEARS_BETWEEN(CURRENT_DATE, p.BIRTH_DATE)) AS AGE, c.ENCOUNTER_ID, c.PRESCRIBED_IN,
       c.DRUG, c.ORDER_STATUS, c.ALLERGY_AS_RECORDED, c.SEVERITY, c.ALLERGY_RECORDED_IN, c.KNOWN_WHERE_PRESCRIBED
FROM   HOSP_CORE.ALLERGY_CONFLICTS c                   -- MongoDB orders x Postgres + MongoDB allergies
JOIN   HOSP_CORE.PATIENT_SUMMARY p ON p.UNIFIED_ID = c.UNIFIED_ID
JOIN   HOSP_CORE.ENCOUNTERS e ON e.ENCOUNTER_ID = c.ENCOUNTER_ID AND e.STATUS = 'in-progress'
ORDER  BY c.KNOWN_WHERE_PRESCRIBED, c.SEVERITY DESC"""
Q_INBED = """SELECT STATUS, COUNT(*) AS PATIENTS FROM HOSP_SRC.MODERN_ENCOUNTERS WHERE STATUS = 'in-progress' GROUP BY STATUS"""

Q_MPI_TOTAL = """SELECT 'all' AS K, COUNT(*) AS RECORDS, COUNT(DISTINCT UNIFIED_ID) AS PEOPLE,
       (SELECT COUNT(*) FROM HOSP_CORE.MATCH_REVIEW_QUEUE) AS REVIEW FROM HOSP_CORE.MPI GROUP BY 'all'"""
Q_FLOW_COUNTS = """SELECT
  (SELECT COUNT(*) FROM HOSP_CORE.PATIENT_RECORDS WHERE SOURCE_SYSTEM = 'LEGACY_HIS') AS LEGACY,
  (SELECT COUNT(*) FROM HOSP_CORE.PATIENT_RECORDS WHERE SOURCE_SYSTEM = 'MODERN_EHR') AS MODERN,
  (SELECT COUNT(*) FROM HOSP_CORE.MPI) AS RECORDS,
  (SELECT COUNT(DISTINCT UNIFIED_ID) FROM HOSP_CORE.MPI) AS PEOPLE,
  (SELECT COUNT(*) FROM HOSP_CORE.MATCH_REVIEW_QUEUE) AS REVIEW,
  (SELECT COUNT(*) FROM HOSP_CORE.NOTE_INDEX) AS NOTES,
  (SELECT COUNT(*) FROM HOSP_CORE.NOTE_VECTORS) AS VECTORS
FROM DUAL"""
Q_AUDIT = """SELECT USER_NAME, START_TIME, SUCCESS, SECS, SQL_TEXT
FROM   HOSP_CONSOLE.AGENT_AUDIT                        -- the two named users' statements (view over EXA_DBA_AUDIT_SQL)
ORDER  BY START_TIME DESC LIMIT 8"""

HEALTH = {"exa": "SELECT 1 AS OK FROM DUAL",
          "pg": f"SELECT COUNT(*) AS N FROM HOSP_LEGACY.PAT_MSTR WHERE PAT_NO = '{HERO_LEGACY}'",
          "mongo": f"SELECT RECORD_ID, COUNT(*) AS N FROM HOSP_SRC.MODERN_PATIENTS WHERE RECORD_ID = '{HERO_EHR}' GROUP BY RECORD_ID",
          "s3": "SELECT MODALITY, COUNT(*) AS N FROM HOSP_SRC.IMAGING_INDEX GROUP BY MODALITY"}

TRACE_SQL = {
    "t_mpi": f"SELECT RECORD_ID, SOURCE_SYSTEM, LINK_SCORE FROM HOSP_CORE.MPI WHERE UNIFIED_ID = {ME}",
    "t_orders": f"SELECT DRUG, DOSE, ORDER_STATUS FROM HOSP_SRC.MODERN_MEDICATIONS WHERE RECORD_ID = '{HERO_EHR}' AND ORDER_STATUS IN ('draft', 'active')",
    "t_allergy": f"SELECT ALLERGY_AS_RECORDED, DRUG_CLASS, SEVERITY FROM HOSP_SRC.LEGACY_ALLERGIES WHERE RECORD_ID = '{HERO_LEGACY}'",
    "t_class": "SELECT DRUG, DRUG_CLASS FROM HOSP_CORE.DRUG_CLASS WHERE DRUG = 'AMOXICILLIN-CLAVULANATE'",
    "t_all": f"SELECT DRUG, ALLERGY_AS_RECORDED, KNOWN_WHERE_PRESCRIBED FROM HOSP_CORE.ALLERGY_CONFLICTS WHERE UNIFIED_ID = {ME}",
}

# name -> SQL; build.py writes these to queries/business/<name>.sql
QUERIES = {"who": Q_WHO, "allergy": Q_ALLERGY, "allergy_ehr": Q_ALLERGY_EHR, "allergy_note": Q_ALLERGY_NOTE,
           "scans": Q_SCANS, "scans_all": Q_SCANS_ALL, "similar": Q_SIMILAR, "similar_text": Q_SIMILAR_TEXT,
           "readm_live": Q_READM_LIVE, "readm_fast": Q_READM_FAST, "chain": Q_CHAIN, "inbed": Q_INBED,
           "mpi_total": Q_MPI_TOTAL, "flow_counts": Q_FLOW_COUNTS, "agent_audit": Q_AUDIT,
           **{f"health_{k}": v for k, v in HEALTH.items()}, **{f"flow_{k}": v for k, v in TRACE_SQL.items()}}
EXPLAIN = {"who": Q_WHO, "allergy": Q_ALLERGY_NOTE, "chain": Q_CHAIN, "readmit": Q_READM_LIVE}
SMOKE = {"queries/business/similar_text.sql": {"vec": "SELECT 0 AS DIM, 1.0 AS VAL FROM DUAL"}}

# ------------------------------------------------------------------ data layer (bound to dash-server by app.py)
_BIND = {}
_NUM = re.compile(r"^-?\d+(\.\d+)?$")


def bind(server, metadata, app_file, loader, has_error):
    _BIND.update(server=server, metadata=metadata, file=app_file, load=loader, has_error=has_error)


def _num(v):
    """DECIMAL arrives as a string; turn numeric strings into numbers for display."""
    if isinstance(v, str) and _NUM.match(v):
        return float(v) if "." in v else int(v)
    return v


def run(name, params=None, path=None, cache=True):
    """Run one SQL file through the dash-server profile. Returns {rows, cols, secs, live, error, at}."""
    t = time.time()
    rows = _BIND["load"](_BIND["server"], _BIND["metadata"], _BIND["file"], path or f"queries/business/{name}.sql",
                         params=params or {})
    secs = time.time() - t
    if not _BIND["has_error"](rows):
        rows = [{k: _num(v) for k, v in r.items()} for r in rows]
        res = {"rows": rows, "cols": list(rows[0]) if rows else [], "secs": secs, "live": True, "error": None,
               "at": time.strftime("%H:%M:%S")}
        if cache:
            CACHE.mkdir(parents=True, exist_ok=True)
            (CACHE / f"{name}.json").write_text(json.dumps(res, default=str))
        return res
    msg = str(rows[0].get("_error"))[:300]
    f = CACHE / f"{name}.json"
    if cache and f.exists():
        res = json.loads(f.read_text())
        res.update(live=False, error=msg)
        return res
    return {"rows": [], "cols": [], "secs": secs, "live": False, "error": msg, "at": None}


def explain_pg(k):
    """EXPLAIN VIRTUAL: the statement each virtual schema would send. Shown so engineers see real pushdown, not a claim."""
    res = run(f"explain_{k}", path=f"explain/{k}.sql")
    out = []
    for r in res["rows"]:
        txt = str(list(r.values())[1]) if len(r) > 1 else ""
        if "FROM JDBC" in txt and "STATEMENT '" in txt:
            out.append(txt.split("STATEMENT '", 1)[1].rstrip("'").replace("''", "'"))
    return "\n\n".join(dict.fromkeys(out))[:3000] or "(no Postgres statement for this question)"


def mpi_rules():
    p = SQLDIR / "20_mpi.sql"
    return p.read_text().split("-- 2.", 1)[1].split("-- 3.", 1)[0].strip()[:2400] if p.exists() else ""


def imaging_view():
    p = SQLDIR / "25_imaging.sql"
    return p.read_text().split("CREATE OR REPLACE VIEW", 2)[1].join(["CREATE OR REPLACE VIEW", ""]).strip() if p.exists() else ""


# ------------------------------------------------------------------ the six questions
QUESTIONS = {
    "who": dict(n=1, ask="Who is Meenakshi Sundaram?", src="Legacy HIS (Postgres) + modern EHR (MongoDB) + PACS (S3), tied by the patient index",
                nodes={"exa", "pg", "mongo", "s3", "mpi"}, edges={"P", "M", "S"}, go="", back="",
                did=["Read her records live from three systems that have never shared an ID: the Branch A HIS, the Branch B EHR and the PACS.",
                     "Resolved them to one person with the patient index: deterministic rules, every link explained.",
                     "Three ways to write the same birth date and name, one answer. Nothing was copied to get it."]),
    "allergy": dict(n=2, ask="Is the prescription drafted now safe for her?", src="Draft order in MongoDB x allergy note in Postgres, read live",
                    nodes={"exa", "pg", "mongo", "mpi"}, edges={"P", "M"}, go="the question", back="1 alert",
                    did=["Read today's draft order from the Branch B EHR and her allergy history from the Branch A HIS, live, in one SQL statement.",
                         "Mapped both to drug classes (amoxicillin-clavulanate is a penicillin) with a formulary table in Exasol.",
                         "The Branch B system on its own holds no allergy for her. Only the fused record shows the conflict."]),
    "scans": dict(n=3, ask="What did her earlier scans show?", src="DICOM header index on Amazon S3, read in place; images shown from S3",
                  nodes={"exa", "s3", "mpi"}, edges={"S"}, go="read index", back="her studies",
                  did=["Read the PACS header index straight from S3 with a read-only key. No load job.",
                       "Matched the DICOM PatientID tags (two different ID schemes) to her through the patient index.",
                       "The images never pass through the database: the page shows them from S3 by signed link."]),
    "similar": dict(n=4, ask="What worked for patients like her?", src="Note vectors in Exasol + allergies and diabetes from both systems + outcomes",
                    nodes={"exa", "pg", "mongo", "vec", "mpi"}, edges={"P", "M"}, go="", back="",
                    did=["Ranked 3,976 clinical notes by similarity to her note from today: cosine similarity as a join and GROUP BY, inside Exasol.",
                         "Kept only diabetic patients over 60 with a penicillin allergy, using facts from BOTH branch systems, live.",
                         "Added what they were given and how it went (stay, readmission) from the system that treated them."]),
    "readmit": dict(n=5, ask="How many patients came back to a different branch?", src="Encounters from both systems, live, then from Exasol's in-memory copy",
                    nodes={"exa", "pg", "mongo", "mpi"}, edges={"P", "M"}, go="", back="",
                    did=["Applied ONE certified definition of a 30-day readmission to every branch: same person, any branch, any system.",
                         "A third of readmissions cross systems or branches, so each branch system alone under-counts them.",
                         "Asked again on a copy built once inside Exasol: same answer, a fraction of the time. Federate first, accelerate what earns it."]),
    "chain": dict(n=6, ask="Who else is at risk right now?", src="Every current order in MongoDB x allergies in Postgres and MongoDB",
                  nodes={"exa", "pg", "mongo", "mpi"}, edges={"P", "M"}, go="", back="",
                  punch=("No pipeline was built for this question.", "Two branch systems, a patient index and one SQL statement found them.",
                         "Legacy + modern &middot; live &middot; zero migration"),
                  did=["Checked every current medication order in the chain against every allergy recorded for the same person, anywhere.",
                       "KNOWN_WHERE_PRESCRIBED = false: the prescribing system had no way to see the allergy.",
                       "The same view is the certified safety check the governed layer exposes (tab 3)."]),
}


def run_question(k, text=""):
    if k == "who":
        return {"main": run("who")}
    if k == "allergy":
        return {"main": run("allergy"), "ehr": run("allergy_ehr"), "note": run("allergy_note")}
    if k == "scans":
        return {"main": run("scans"), "all": run("scans_all")}
    if k == "similar":
        text = (text or "").strip()
        if text:
            vec, esecs = embed.values_sql(text)
            res = run("similar_text", params={"vec": vec}, cache=False)
            return {"main": res, "sql": Q_SIMILAR_TEXT.replace("{vec!r}", vec[:220] + " …"), "text": text, "embed_secs": esecs}
        return {"main": run("similar"), "sql": Q_SIMILAR}
    if k == "readmit":
        return {"main": run("readm_live"), "fast": run("readm_fast")}
    return {"main": run("chain"), "inbed": run("inbed")}


def question_sql(k, out):
    return {"who": Q_WHO, "allergy": Q_ALLERGY, "scans": Q_SCANS, "similar": (out or {}).get("sql", Q_SIMILAR),
            "readmit": Q_READM_LIVE, "chain": Q_CHAIN}[k]


# ------------------------------------------------------------------ the diagram
SHOWN = {"P": "A", "M": "B", "S": "C"}
LEGEND = {"P": "Legacy HIS (hospital information system): the official PostgreSQL virtual schema (JDBC) pushes each query down to the 2009-era database, read-only",
          "M": "Modern EHR (electronic health record): the MongoDB virtual schema turns nested documents (allergies, medications, observations) into related SQL tables",
          "S": "PACS (picture archiving and communication system) on S3: Exasol reads the DICOM header index in place; the images stay as files"}


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


def legend(active):
    q = QUESTIONS.get(active)
    edges = sorted(q["edges"] if q else LEGEND, key=lambda e: SHOWN[e])
    return "".join(f'<div class="hint" style="margin-top:.4rem"><b>{SHOWN[e]}</b> &middot; {LEGEND[e]}</div>' for e in edges)


# ------------------------------------------------------------------ answer visuals
def big3(items):
    return '<div class="big3">' + "".join(
        f'<div class="b3{" hl" if hl else ""}"><div class="v">{v}</div><div class="k">{k}</div></div>' for v, k, hl in items) + "</div>"


def esc(v):
    return _h.escape("" if v is None else str(v))


def _false(v):
    return str(v).lower() == "false"


def answer(k, out):
    """Returns (nums, html). For "scans" the image cards are Dash components built in app.py; html is only the footer."""
    res = out["main"]
    rows = res["rows"]
    vis = ""
    if k == "who":
        systems = {r["SOURCE_LABEL"] for r in rows}
        ids = {r["RECORD_ID"] for r in rows}
        score = max((r.get("LINK_SCORE") or 0) for r in rows) if rows else 0
        nums = [(f"{len(systems)}", "systems hold her data, none shares an ID", False),
                (f"{len(ids)} &rarr; 1", "record and image IDs resolved to one person", True),
                (f"{res['secs']:.1f} s", "live, end to end", False)]
        cls = {"Legacy HIS": "legacy", "Modern EHR": "modern", "PACS on S3": "pacs"}
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
        nums = [("1" if a else "0", "conflict found for her", True),
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
                vis += f'<div class="quote">Discharge summary {esc(note["VISIT_NO"])}, {esc(note["ADM_DT"])}: &ldquo;&hellip;{esc(str(note["SUMM_TXT"])[160:420])}&hellip;&rdquo;</div>'
        else:
            vis = '<div class="hint">No conflict found.</div>'
    elif k == "scans":
        tot = out["all"]["rows"]
        n = sum(int(r["STUDIES"]) for r in tot)
        mb = sum(float(r["BYTES"] or 0) for r in tot) / 1e6
        nums = [(f"{n}", f"studies in the PACS ({mb:,.0f} MB of DICOM)", False), (f"{len(rows)}", "are hers, under two different patient IDs", True),
                ("0", "pixels passed through the database", False)]
        vis = ('<div class="hint" style="font-size:.8rem">Real de-identified images from The Cancer Imaging Archive (COVID-19-AR and UPENN-GBM, CC BY 4.0), '
               'relabelled to the synthetic patient. Today\'s X-ray is acquired and not yet reported.</div>')
    elif k == "similar":
        ls = [float(r["LENGTH_OF_STAY"] or 0) for r in rows]
        ra = sum(1 for r in rows if str(r["READMITTED_30D"]).lower() == "true")
        nums = [("3,976", "clinical notes compared by meaning", False),
                (f"{len(rows)}", "similar diabetic patients over 60, penicillin-allergic", True),
                (f"{res['secs']:.1f} s", "live, end to end" + (f" (+{out['embed_secs']:.1f} s to embed the text)" if out.get("embed_secs") else ""), False)]
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
        hidden = sum(1 for r in rows if _false(r["KNOWN_WHERE_PRESCRIBED"]))
        nums = [(f"{int(inbed)}", "patients in a bed right now (modern EHR)", False),
                (f"{len(rows)}", "have an order that contradicts a recorded allergy", True),
                (f"{hidden}", "of them: the allergy is missing from the system that wrote the order", False)]
        vis = "".join(
            f'<div class="cu"><div><div class="nm">{esc(r["PATIENT_NAME"])} &middot; {int(r["AGE"])} y &middot; {esc(r["ENCOUNTER_ID"])}</div>'
            f'<div class="mt" style="font-style:normal">{esc(r["DRUG"])} ({esc(r["ORDER_STATUS"])}) &times; &ldquo;{esc(r["ALLERGY_AS_RECORDED"])}&rdquo; '
            f'in the {"legacy HIS" if r["ALLERGY_RECORDED_IN"] == "LEGACY_HIS" else "EHR"}'
            + (' &middot; <b style="color:#C8102E">no allergy on file in the system that wrote the order</b>' if _false(r["KNOWN_WHERE_PRESCRIBED"])
               else ' &middot; <b style="color:#12796A">allergy on file where prescribed</b>') + '</div></div></div>'
            for r in rows)
    return nums, vis


def answer_head(k, out):
    q = QUESTIONS[k]
    nums, vis = answer(k, out)
    cached = "" if out["main"]["live"] else f'<div class="cached">Live source unavailable: showing the last good run. ({esc(out["main"].get("error"))[:140]})</div>'
    return f'<div class="q">{q["ask"]}</div><div class="src">{q["src"]}</div>{big3(nums)}', vis + cached


def answer_tail(k):
    q = QUESTIONS[k]
    punch = (f'<div class="punch"><div class="pt">{q["punch"][0]}</div><div class="pv">{q["punch"][1]}</div>'
             f'<div class="ps">{q["punch"][2]}</div></div>') if q.get("punch") else ""
    return punch + f'<div class="did" style="margin-top:.8rem"><div class="k">What Exasol did</div><ul>{"".join(f"<li>{d}</li>" for d in q["did"])}</ul></div>'
