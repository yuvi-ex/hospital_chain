#!/usr/bin/env python3
"""Generate the hospital chain: one synthetic population, written into the systems that really hold it.

  Branch A (BRA)    legacy HIS only            -> Postgres  branch_a_his.his.*   (2009-era schema, dates as text)
  Branch B (BRB)  modern EHR only            -> MongoDB   ehr.patients / ehr.encounters (FHIR-flavoured docs)
  Branch C (BRC)  migrating: visits before 2024-04-01 in the legacy HIS, after it in the modern EHR

The same person can exist in several systems under different IDs, with the mess real registrations have:
initials for surnames, spelling variants, day/month swapped birth dates, two-digit years, missing dates.
The ground truth (which record is which person) is written to data/out/truth_*.csv and is NEVER loaded
into Exasol: the matching in the demo has to earn its answer, and the truth file is how we check it.
Everything written to the two systems is also saved as files: data/out/sources/legacy_his/<table>.csv and
data/out/sources/modern_ehr/<collection>.jsonl, so the data set can be read without running anything.

Deterministic (seeded). Re-running replaces the data in both systems.
  .venv/bin/python data/generate.py
"""
import csv
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg
from psycopg import sql
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig  # noqa: E402

R = random.Random(20261026)
TODAY = date(2026, 10, 26)
CUTOVER = date(2024, 4, 1)          # Branch C moved to the modern EHR on this day
N_PEOPLE = 1200
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# Both systems run in podman INSIDE the Exasol VM (setup/00_sources_vm.sh): the Mac reaches them on the VM's IP.
# Local demo containers only: these default passwords never leave the VM (set in setup/00_sources_vm.sh).
# --files-only: write data/out without touching the databases (to check that a change reproduces the data set)
FILES_ONLY = "--files-only" in sys.argv
if not FILES_ONLY:
    VM_IP = hcconfig.vm_ip()
    PG = (f"postgresql://his_admin:{hcconfig.secret('HC_PG_ADMIN_PASSWORD')}@{VM_IP}:{hcconfig.PG_PORT}/branch_a_his"
          "?connect_timeout=10")
    MONGO = (f"mongodb://root:{hcconfig.secret('HC_MONGO_ROOT_PASSWORD')}@{VM_IP}:{hcconfig.MONGO_PORT}/"
             "?authSource=admin&directConnection=true&serverSelectionTimeoutMS=10000")
SOURCES = OUT / "sources"
PG_COLS = {"pat_mstr": "pat_no branch_cd pat_nm sex dob_txt age_yrs ph_no city reg_dt",
           "visit_hdr": "visit_no pat_no branch_cd visit_typ dept_cd adm_dt dis_dt dx_cd dx_desc doc_cd",
           "alrgy_txt": "pat_no alrgy_note entry_dt", "lab_rslt": "visit_no test_cd rslt_val unit rslt_dt",
           "rx_line": "visit_no line_no drug_nm dose_txt", "dis_summ": "visit_no summ_txt"}


def save_table(name, rows):
    """The legacy HIS tables as CSV with a header (empty string = NULL), exactly the rows loaded into Postgres."""
    (SOURCES / "legacy_his").mkdir(parents=True, exist_ok=True)
    with open(SOURCES / "legacy_his" / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(PG_COLS[name].split())
        w.writerows(["" if v is None else v for v in row] for row in rows)


def save_collection(name, docs):
    """The modern EHR collections as JSON Lines, one document per line, exactly as inserted into MongoDB."""
    (SOURCES / "modern_ehr").mkdir(parents=True, exist_ok=True)
    with open(SOURCES / "modern_ehr" / f"{name}.jsonl", "w") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False, default=lambda v: v.isoformat()) + "\n")
# Branches and places are deliberately generic: this is a fictional chain, not a portrait of a real one.
CITY = {"BRA": ("City A", "State A"), "BRB": ("City B", "State B"), "BRC": ("City C", "State C")}
DEPT = {"PULM": "Pulmonology", "CARD": "Cardiology", "NEURO": "Neurology", "MED": "General Medicine",
        "ENDO": "Endocrinology", "ONCO": "Oncology", "ORTHO": "Orthopaedics", "ER": "Emergency"}

# ----------------------------------------------------------------------------- names
F_GIVEN = ["Meenakshi", "Lakshmi", "Priya", "Kavitha", "Anitha", "Revathi", "Deepa", "Sangeetha", "Fatima", "Ayesha",
           "Sunita", "Geetha", "Padma", "Radha", "Shanthi", "Vijaya", "Kalpana", "Nirmala", "Usha", "Saroja",
           "Divya", "Swathi", "Harini", "Bhavani", "Rukmini", "Mary", "Jessy", "Nandini", "Shobha", "Yamuna"]
M_GIVEN = ["Ramesh", "Suresh", "Venkatesh", "Srinivasan", "Karthik", "Arun", "Mohammed", "Abdul", "Rajesh", "Ganesh",
           "Murugan", "Senthil", "Prakash", "Anand", "Vijay", "Krishnan", "Balaji", "Naveen", "Joseph", "Thomas",
           "Mahesh", "Ravi", "Sanjay", "Imran", "Gopal", "Selvam", "Harish", "Manoj", "Dinesh", "Raghavan"]
SURNAMES = ["Sundaram", "Raghunathan", "Iyer", "Reddy", "Rao", "Naidu", "Pillai", "Nair", "Menon", "Krishnamurthy",
            "Subramanian", "Venkataraman", "Gowda", "Shetty", "Khan", "Sheikh", "Varghese", "Fernandes", "Murthy",
            "Chandrasekar", "Balasubramanian", "Ramaswamy", "Natarajan", "Hegde", "Patil", "Kulkarni", "Ali",
            "Joseph", "Thomas", "Prasad"]
VARIANTS = {"Meenakshi": "Minakshi", "Lakshmi": "Laxmi", "Srinivasan": "Sreenivasan", "Mohammed": "Mohamed",
            "Venkatesh": "Venkatesan", "Kavitha": "Kavita", "Sangeetha": "Sangita", "Revathi": "Revathy",
            "Geetha": "Gita", "Shanthi": "Shanti", "Karthik": "Karthick", "Abdul": "Abdhul", "Murugan": "Murugam",
            "Senthil": "Senthill", "Ayesha": "Aisha", "Harini": "Harinee", "Raghavan": "Ragavan", "Rajesh": "Rajeshh"}

# ----------------------------------------------------------------------------- clinical vocabulary
# condition -> dept, ICD-10, display, inpatient probability, imaging modality (None = no imaging)
ACUTE = {
    "cap":    ("PULM", "J18.9", "Pneumonia, unspecified organism", .85, "CXR"),
    "copd":   ("PULM", "J44.1", "COPD with acute exacerbation", .75, "CXR"),
    "hf":     ("CARD", "I50.9", "Heart failure, unspecified", .85, "CXR"),
    "nstemi": ("CARD", "I21.4", "Non-ST elevation myocardial infarction", 1.0, None),
    "stroke": ("NEURO", "I63.9", "Cerebral infarction, unspecified", 1.0, "MR"),
    "glioma": ("ONCO", "C71.9", "Malignant neoplasm of brain", .4, "MR"),
    "dka":    ("ENDO", "E11.10", "Type 2 diabetes with ketoacidosis", 1.0, None),
    "uti":    ("MED", "N39.0", "Urinary tract infection", .55, None),
    "covid":  ("PULM", "U07.1", "COVID-19", .6, "CT"),
    "asthma": ("PULM", "J45.901", "Asthma with acute exacerbation", .35, "CXR"),
    "dfu":    ("ENDO", "E11.621", "Type 2 diabetes with foot ulcer", .5, None),
    "review": ("ENDO", "E11.9", "Type 2 diabetes mellitus, routine review", 0.0, None),
    "htn":    ("CARD", "I10", "Essential hypertension, review", 0.0, None),
}
ABX_PEN = ["Amoxicillin-clavulanate", "Piperacillin-tazobactam", "Amoxicillin", "Ampicillin"]
ABX_ALT = ["Levofloxacin", "Doxycycline", "Azithromycin", "Ceftriaxone", "Clarithromycin"]
DOSE = {"Amoxicillin-clavulanate": "625 mg TDS", "Piperacillin-tazobactam": "4.5 g IV q8h", "Amoxicillin": "500 mg TDS",
        "Ampicillin": "1 g IV q6h", "Levofloxacin": "750 mg OD", "Doxycycline": "100 mg BD", "Azithromycin": "500 mg OD",
        "Ceftriaxone": "2 g IV OD", "Clarithromycin": "500 mg BD", "Metformin": "500 mg BD", "Insulin glargine": "18 U HS",
        "Furosemide": "40 mg OD", "Aspirin": "75 mg OD", "Atorvastatin": "40 mg HS", "Salbutamol nebulisation": "5 mg q6h",
        "Prednisolone": "40 mg OD", "Clopidogrel": "75 mg OD", "Enoxaparin": "60 mg SC BD", "Nitrofurantoin": "100 mg BD",
        "Co-trimoxazole": "960 mg BD", "Temozolomide": "150 mg/m2 D1-5", "Dexamethasone": "4 mg TDS",
        "Paracetamol": "1 g QID", "Ibuprofen": "400 mg TDS", "Remdesivir": "100 mg IV OD", "Insulin infusion": "0.1 U/kg/h",
        "Telmisartan": "40 mg OD", "Amlodipine": "5 mg OD", "Diclofenac": "50 mg BD", "Alteplase": "0.9 mg/kg IV"}
ALLERGENS = [("PENICILLIN", ["PENICILLIN - {r} ({y})", "ALLERGIC TO AMOXY {y}", "PEN ALLERGY - {r}", "AMOXICILLIN -> {r}"],
              "Penicillin", ["anaphylaxis", "urticaria", "rash"]),
             ("SULFONAMIDE", ["SULPHA - {r}", "SULFA DRUGS ({r})"], "Sulfonamide antibiotics", ["rash", "Stevens-Johnson syndrome"]),
             ("NSAID", ["NSAID - {r}", "IBUPROFEN/DICLOFENAC - {r}"], "NSAIDs", ["bronchospasm", "angioedema"]),
             ("CEPHALOSPORIN", ["CEFTRIAXONE - {r}"], "Ceftriaxone", ["rash"])]


def pick(seq):
    return R.choice(seq)


# ----------------------------------------------------------------------------- people
class Person:
    pass


def make_people():
    people = []
    for i in range(N_PEOPLE):
        p = Person()
        p.pid = f"T{i:05d}"                         # truth id, never loaded
        p.sex = "F" if R.random() < .5 else "M"
        p.given = pick(F_GIVEN if p.sex == "F" else M_GIVEN)
        p.family = pick(SURNAMES)
        age = int(min(92, max(19, R.gauss(56, 16))))
        p.dob = TODAY - timedelta(days=age * 365 + R.randint(0, 364))
        # synthetic and undiallable: 00000 + a number unique per person (the draw is kept so the seeded data stays the same)
        R.randint(100000000, 999999999)
        p.mobile = f"00000{len(people):05d}"
        p.home = R.choices(["BRA", "BRB", "BRC"], [.40, .35, .25])[0]
        p.dm = age > 40 and R.random() < .34
        p.htn = age > 40 and R.random() < .38
        p.copd = age > 50 and R.random() < .12
        p.asthma = R.random() < .07
        p.cad = age > 50 and R.random() < .15
        p.glioma = R.random() < .015
        p.allergy = None
        if R.random() < .16:
            p.allergy = R.choices(ALLERGENS, [.6, .2, .15, .05])[0]
        p.allergy_year = R.randint(2012, 2022)
        p.allergy_reaction = pick(p.allergy[3]) if p.allergy else None
        people.append(p)
    return people


def hero(people):
    """Mrs. Meenakshi Sundaram: penicillin allergy known only to Branch A's legacy HIS, now admitted in Branch B."""
    p = people[731]
    p.sex, p.given, p.family = "F", "Meenakshi", "Sundaram"
    p.dob, p.mobile, p.home = date(1958, 3, 14), "0000012345", "BRA"
    p.dm, p.htn, p.copd, p.asthma, p.cad, p.glioma = True, True, False, False, False, False
    p.allergy = ALLERGENS[0]
    p.allergy_year, p.allergy_reaction = 2019, "anaphylaxis"
    p.hero = True
    return p


def condition_for(p):
    w = {"cap": 6 + 6 * p.dm, "copd": 18 * p.copd, "hf": 3 + 8 * p.cad, "nstemi": 1 + 5 * p.cad, "stroke": 1.5 + 3 * p.htn,
         "glioma": 60 * p.glioma, "dka": 4 * p.dm, "uti": 5 + 3 * p.dm, "covid": 3, "asthma": 16 * p.asthma, "dfu": 3 * p.dm,
         "review": 14 * p.dm, "htn": 10 * p.htn}
    keys = [k for k in w if w[k] > 0]
    return R.choices(keys, [w[k] for k in keys])[0]


def meds_for(cond, p, allergy_known):
    """Treatment given. Clinicians who KNEW about a penicillin allergy chose an alternative; the others did not."""
    pen_ok = not (p.allergy and p.allergy[0] == "PENICILLIN" and allergy_known)
    abx = pick(ABX_PEN + ABX_ALT) if pen_ok else pick(ABX_ALT)
    base = {"cap": [abx, "Paracetamol"], "copd": [abx, "Salbutamol nebulisation", "Prednisolone"],
            "hf": ["Furosemide", "Enoxaparin"], "nstemi": ["Aspirin", "Clopidogrel", "Atorvastatin", "Enoxaparin"],
            "stroke": ["Aspirin", "Atorvastatin"] + (["Alteplase"] if R.random() < .2 else []),
            "glioma": ["Temozolomide", "Dexamethasone"], "dka": ["Insulin infusion"], "uti": [pick(["Nitrofurantoin", "Co-trimoxazole", "Ceftriaxone"])],
            "covid": ["Remdesivir", "Dexamethasone", "Enoxaparin"], "asthma": ["Salbutamol nebulisation", "Prednisolone"],
            "dfu": [abx, "Insulin glargine"], "review": ["Metformin"], "htn": [pick(["Telmisartan", "Amlodipine"])]}[cond]
    if p.dm and cond not in ("review", "dka"):
        base.append("Metformin" if R.random() < .6 else "Insulin glargine")
    if cond in ("dfu", "uti") and R.random() < .2:
        base.append(pick(["Ibuprofen", "Diclofenac"]))
    return base


# ----------------------------------------------------------------------------- notes
SYMPTOMS = {
    "cap": ["fever for {d} days with productive cough and breathlessness", "high-grade fever, cough with yellow sputum and right-sided chest pain",
            "breathlessness on exertion, fever with chills and cough for {d} days"],
    "copd": ["worsening breathlessness and wheeze for {d} days, increased sputum volume", "acute dyspnoea with purulent sputum on background COPD"],
    "hf": ["progressive breathlessness, orthopnoea and bilateral leg swelling for {d} days", "paroxysmal nocturnal dyspnoea and reduced exercise tolerance"],
    "nstemi": ["central chest pain radiating to the left arm for {h} hours with sweating", "retrosternal chest tightness at rest with nausea"],
    "stroke": ["sudden onset right-sided weakness and slurred speech {h} hours before arrival", "acute left facial droop and left arm weakness"],
    "glioma": ["follow-up of high-grade glioma, new headaches and word-finding difficulty", "seizure at home on background of treated glioma"],
    "dka": ["vomiting, abdominal pain and drowsiness, missed insulin doses", "polyuria, polydipsia and rapid breathing for {d} days"],
    "uti": ["dysuria, frequency and fever for {d} days", "suprapubic pain with fever and confusion"],
    "covid": ["fever, dry cough and loss of taste for {d} days, SARS-CoV-2 RT-PCR positive", "breathlessness and desaturation with COVID-19 positive test"],
    "asthma": ["acute wheeze and chest tightness after viral illness", "nocturnal cough and breathlessness, poor inhaler technique"],
    "dfu": ["non-healing ulcer on the right great toe for {w} weeks", "foot ulcer with surrounding cellulitis and discharge"],
    "review": ["routine diabetes review, no acute complaints", "diabetes follow-up, occasional fatigue, adherence fair"],
    "htn": ["blood pressure review, occasional headaches", "hypertension follow-up, home readings elevated"],
}
FINDINGS = {
    "cap": ["crackles at the {s} lung base, SpO2 {o}% on room air", "bronchial breathing over the {s} lower zone, SpO2 {o}%"],
    "copd": ["prolonged expiration with diffuse wheeze, SpO2 {o}%", "hyperinflated chest, scattered rhonchi, SpO2 {o}%"],
    "hf": ["raised JVP, bibasal crackles and pitting oedema, SpO2 {o}%", "S3 gallop, bilateral crackles, SpO2 {o}%"],
    "nstemi": ["ST depression in V4-V6, troponin raised", "dynamic T-wave inversion, troponin elevated"],
    "stroke": ["NIHSS {n}, power 2/5 right upper limb", "NIHSS {n}, dysarthria and left hemiparesis"],
    "glioma": ["expressive dysphasia, no focal motor deficit", "post-ictal drowsiness, mild right pronator drift"],
    "dka": ["Kussmaul breathing, capillary glucose {g} mg/dL, ketones high", "dehydrated, pH 7.1, glucose {g} mg/dL"],
    "uti": ["renal angle tenderness, urine dipstick nitrite positive", "febrile, suprapubic tenderness, leucocytes in urine"],
    "covid": ["bilateral crepitations, SpO2 {o}%", "tachypnoea, SpO2 {o}% on room air"],
    "asthma": ["widespread wheeze, peak flow 55% of predicted", "silent chest absent, wheeze bilaterally, SpO2 {o}%"],
    "dfu": ["2 cm ulcer with slough, foot pulses diminished", "ulcer with erythema to the mid-foot, probe-to-bone negative"],
    "review": ["HbA1c {a}%, BMI 28, feet intact", "HbA1c {a}%, no retinopathy on last screen"],
    "htn": ["BP 156/94, no end-organ damage", "BP 148/92, fundi normal"],
}
IMAGING_TXT = {"CXR": ["chest X-ray: {s} lower lobe consolidation", "chest X-ray: patchy opacities, {s} base",
                       "chest X-ray: cardiomegaly with upper lobe diversion", "chest X-ray: hyperinflation, no consolidation"],
               "CT": ["CT chest: bilateral ground-glass opacities", "CT chest: peripheral ground-glass with consolidation"],
               "MR": ["MRI brain: acute infarct on diffusion imaging", "MRI brain: enhancing lesion, stable compared with prior"]}
OUTCOME = ["Improved and discharged on day {los}.", "Responded to treatment, discharged on day {los} with follow-up in 2 weeks.",
           "Slow recovery, discharged on day {los}.", "Stable, discharged on day {los} with home oxygen review."]


def note_text(cond, p, meds, los, modality, legacy):
    s = pick(["right", "left"])
    fill = dict(d=R.randint(2, 7), h=R.randint(1, 8), w=R.randint(2, 6), s=s, o=R.randint(84, 95), n=R.randint(4, 16),
                g=R.randint(320, 560), a=round(R.uniform(6.8, 10.5), 1), los=los)
    parts = [f"{'Known diabetic. ' if p.dm and cond != 'review' else ''}{'Hypertensive. ' if p.htn and cond != 'htn' else ''}"
             f"Presented with {pick(SYMPTOMS[cond]).format(**fill)}.",
             f"On examination {pick(FINDINGS[cond]).format(**fill)}."]
    if modality:
        parts.append(pick(IMAGING_TXT[modality]).format(**fill).capitalize() + ".")
    parts.append("Treated with " + ", ".join(meds) + ".")
    if los:
        parts.append(pick(OUTCOME).format(**fill))
    t = " ".join(parts)
    return t.upper() if legacy and R.random() < .5 else t


# ----------------------------------------------------------------------------- encounters
def system_for(branch, d):
    return "legacy" if branch == "BRA" or (branch == "BRC" and d < CUTOVER) else "modern"


def make_encounters(people, h):
    enc = []
    for p in people:
        n = max(1, int(R.expovariate(1 / 5)))
        second = R.choice([b for b in ("BRA", "BRB", "BRC") if b != p.home]) if R.random() < .18 else None
        dates = sorted(TODAY - timedelta(days=R.randint(5, 3600)) for _ in range(n))
        for d in dates:
            branch = second if second and R.random() < .35 else p.home
            enc.append(new_enc(p, branch, d))
        # readmissions: some inpatient stays are followed by another admission within 30 days, often elsewhere
    extra = []
    for e in enc:
        if e["ip"] and e["discharge"] and R.random() < .09:
            p = e["person"]
            gap = R.randint(2, 29)
            d2 = e["discharge"] + timedelta(days=gap)
            if d2 >= TODAY:
                continue
            branch = R.choice([b for b in ("BRA", "BRB", "BRC") if b != e["branch"]]) if R.random() < .45 else e["branch"]
            extra.append(new_enc(p, branch, d2, force_ip=True, cond=e["cond"] if R.random() < .6 else None))
    enc += extra
    # patients in a bed right now (modern EHR shows them as in-progress)
    # ...a third of them with an allergy recorded in the legacy HIS (people who were once treated in Branch A)
    allergic = [p for p in people if p.allergy and p.home == "BRA" and p is not h]
    for p in R.sample(allergic, 16) + R.sample(people, 30):
        if p is h:
            continue
        cond = pick(["cap", "copd", "dfu", "uti", "cap"]) if p.allergy else None
        enc.append(new_enc(p, R.choice(["BRB", "BRC"]), TODAY - timedelta(days=R.randint(0, 4)), force_ip=True, current=True, cond=cond))
    # the hero: 2019 pneumonia in Branch A (allergy recorded there), and today in Branch B
    enc.append(new_enc(h, "BRA", date(2019, 6, 11), force_ip=True, cond="cap", los=6, hero_old=True))
    enc.append(new_enc(h, "BRA", date(2022, 2, 3), cond="review"))
    enc.append(new_enc(h, "BRB", TODAY, force_ip=True, cond="cap", current=True, hero_now=True))
    return enc


def new_enc(p, branch, d, force_ip=False, cond=None, current=False, los=None, hero_old=False, hero_now=False):
    cond = cond or condition_for(p)
    dept, icd, disp, ip_p, modality = ACUTE[cond]
    ip = force_ip or R.random() < ip_p
    if ip and cond in ("review", "htn"):
        cond = "cap" if p.dm else "uti"
        dept, icd, disp, ip_p, modality = ACUTE[cond]
    los = los or (max(1, int(R.gauss(5 + 2 * (cond in ("stroke", "hf", "covid")), 2.5))) if ip else 0)
    discharge = None if current else (d + timedelta(days=los) if ip else d)
    if discharge and discharge > TODAY:
        discharge, current = None, True
    sysname = system_for(branch, d)
    # does the treating clinician KNOW about the allergy? only if it is recorded in THIS system
    return dict(person=p, branch=branch, date=d, cond=cond, dept=dept if ip or cond in ("review", "htn") else ("ER" if R.random() < .3 else dept),
                icd=icd, disp=disp, ip=ip, los=los if ip else 0, discharge=discharge, current=current, modality=modality,
                system=sysname, hero_old=hero_old, hero_now=hero_now)


# ----------------------------------------------------------------------------- identity, per system
def legacy_name(p):
    g = VARIANTS.get(p.given, p.given) if R.random() < .12 else p.given
    style = R.random()
    if style < .55:
        return f"{g.upper()} {p.family[0]}"                       # MEENAKSHI S (initial for surname)
    if style < .75:
        return f"{p.family[0]}. {g.upper()}"                       # S. MEENAKSHI
    return f"{g.upper()} {p.family.upper()}"


def legacy_dob(p):
    r = R.random()
    if r < .04:
        return None, TODAY.year - p.dob.year                        # never captured: age only
    if r < .12:
        return p.dob.strftime("%d-%m-%y"), None                     # two-digit year
    if r < .17 and p.dob.day <= 12:
        return p.dob.strftime("%m/%d/%Y"), None                     # day and month swapped at the desk
    return p.dob.strftime("%d/%m/%Y"), None


def modern_name(p):
    g = VARIANTS.get(p.given, p.given) if R.random() < .06 else p.given
    return g, p.family


def fake_landline():
    """A landline instead of a mobile, as front desks often record. The 000 area code makes it undiallable."""
    R.randint(40, 80)                       # (kept: the draw that used to pick an area code keeps the seeded data the same)
    return f"000-{R.randint(2000000, 2999999)}"


def build(people, h, enc):
    legacy_pat, modern_pat, truth = {}, {}, []
    seq = {"BRA": 1000, "BRC": 5000}
    mseq = {"BRB": 100000, "BRC": 300000}
    for e in sorted(enc, key=lambda x: x["date"]):
        p = e["person"]
        if e["system"] == "legacy":
            k = (p.pid, e["branch"])            # each legacy branch registers the patient again: duplicates across sites
            if k not in legacy_pat:
                seq[e["branch"]] += R.randint(1, 9)
                yr = max(2009, e["date"].year - R.randint(0, 2))
                pat_no = f"{e['branch']}/{yr}/{seq[e['branch']]:06d}"
                if getattr(p, "hero", False) and e["branch"] == "BRA":
                    pat_no = "BRA/2014/000731"
                dob_txt, age = legacy_dob(p)
                if getattr(p, "hero", False):
                    dob_txt, age = "14/03/1958", None
                legacy_pat[k] = dict(PAT_NO=pat_no, BRANCH_CD=e["branch"], PAT_NM=("MEENAKSHI S" if getattr(p, "hero", False) else legacy_name(p)),
                                     SEX=p.sex, DOB_TXT=dob_txt, AGE_YRS=age,
                                     PH_NO=(p.mobile if R.random() < .8 else fake_landline()),
                                     CITY=CITY[e["branch"]][0].upper(), REG_DT=e["date"].strftime("%d/%m/%Y"), person=p)
                truth.append((pat_no, "LEGACY_HIS", p.pid))
            e["rec"] = legacy_pat[k]["PAT_NO"]
        else:
            if p.pid not in modern_pat:          # the modern EHR is one database for BRB + BRC: one record per person
                mseq[e["branch"]] += R.randint(1, 37)
                mid = f"{e['branch']}-P-{mseq[e['branch']]:06d}"
                if getattr(p, "hero", False):
                    mid = "BRB-P-108842"
                g, f = modern_name(p)
                modern_pat[p.pid] = dict(_id=mid, mrn=mid, given=g, family=f, person=p, branch=e["branch"], registered=e["date"])
                truth.append((mid, "MODERN_EHR", p.pid))
            e["rec"] = modern_pat[p.pid]["_id"]
    return legacy_pat, modern_pat, truth


# ----------------------------------------------------------------------------- write: Postgres
DDL = """
DROP SCHEMA IF EXISTS his CASCADE;
CREATE SCHEMA his;
-- 2009-era HIS: short upper-case names, dates stored as text, free-text allergies.
CREATE TABLE his.pat_mstr (pat_no VARCHAR(20) PRIMARY KEY, branch_cd CHAR(3), pat_nm VARCHAR(60), sex CHAR(1),
  dob_txt VARCHAR(12), age_yrs SMALLINT, ph_no VARCHAR(15), city VARCHAR(30), reg_dt VARCHAR(10));
CREATE TABLE his.visit_hdr (visit_no VARCHAR(20) PRIMARY KEY, pat_no VARCHAR(20), branch_cd CHAR(3), visit_typ CHAR(2),
  dept_cd VARCHAR(6), adm_dt VARCHAR(10), dis_dt VARCHAR(10), dx_cd VARCHAR(8), dx_desc VARCHAR(80), doc_cd VARCHAR(8));
CREATE TABLE his.alrgy_txt (pat_no VARCHAR(20), alrgy_note VARCHAR(200), entry_dt VARCHAR(10));
CREATE TABLE his.lab_rslt (visit_no VARCHAR(20), test_cd VARCHAR(10), rslt_val VARCHAR(12), unit VARCHAR(10), rslt_dt VARCHAR(10));
CREATE TABLE his.rx_line (visit_no VARCHAR(20), line_no SMALLINT, drug_nm VARCHAR(60), dose_txt VARCHAR(30));
CREATE TABLE his.dis_summ (visit_no VARCHAR(20), summ_txt TEXT);
"""


def write_pg(legacy_pat, enc):
    vis, alr, lab, rx, summ, notes = [], [], [], [], [], []
    n = 0
    for e in enc:
        if e["system"] != "legacy":
            continue
        p = e["person"]
        n += 1
        vno = f"{e['branch']}V{e['date']:%y}{n:06d}"
        e["visit_id"] = vno
        typ = "IP" if e["ip"] else ("ER" if e["dept"] == "ER" else "OP")
        vis.append((vno, e["rec"], e["branch"], typ, e["dept"], e["date"].strftime("%d/%m/%Y"),
                    e["discharge"].strftime("%d/%m/%Y") if e["discharge"] else None, e["icd"], e["disp"].upper()[:80],
                    f"DR{R.randint(100, 180)}"))
        known = bool(p.allergy) and e["date"].year >= p.allergy_year
        meds = meds_for(e["cond"], p, known)
        if e.get("hero_old"):
            meds = ["Levofloxacin", "Paracetamol", "Metformin"]
        e["meds"] = meds
        for i, m in enumerate(meds, 1):
            rx.append((vno, i, m.upper(), DOSE.get(m, "")))
        if p.dm:
            lab.append((vno, "HBA1C", f"{R.uniform(6.6, 10.8):.1f}", "%", e["date"].strftime("%d/%m/%Y")))
        if e["ip"]:
            lab.append((vno, "CREAT", f"{R.uniform(.6, 2.4):.2f}", "MG/DL", e["date"].strftime("%d/%m/%Y")))
            txt = note_text(e["cond"], p, meds, e["los"], e["modality"], legacy=True)
            if e.get("hero_old"):
                txt = ("KNOWN DIABETIC, HYPERTENSIVE. PRESENTED WITH FEVER FOR 4 DAYS, PRODUCTIVE COUGH AND BREATHLESSNESS. "
                       "ON EXAMINATION CRACKLES AT THE RIGHT LUNG BASE, SPO2 90% ON ROOM AIR. CHEST X-RAY: RIGHT LOWER LOBE CONSOLIDATION. "
                       "STARTED ON AMOXICILLIN-CLAVULANATE IV; WITHIN 20 MINUTES DEVELOPED STRIDOR, HYPOTENSION AND GENERALISED URTICARIA - "
                       "ANAPHYLAXIS. TREATED WITH IM ADRENALINE. SWITCHED TO LEVOFLOXACIN. IMPROVED AND DISCHARGED ON DAY 6. "
                       "PENICILLIN ALLERGY - DO NOT GIVE BETA-LACTAMS WITHOUT ALLERGY REVIEW.")
            summ.append((vno, txt))
            notes.append(dict(NOTE_ID=f"L:{vno}", SOURCE="LEGACY_HIS", RECORD_ID=e["rec"], ENCOUNTER_ID=vno, NOTE_TEXT=txt))
    for (pid, br), r in legacy_pat.items():
        p = r["person"]
        if p.allergy and R.random() < (1.0 if getattr(p, "hero", False) else .9):
            tmpl = pick(p.allergy[1])
            note = tmpl.format(r=p.allergy_reaction.upper(), y=p.allergy_year)
            if getattr(p, "hero", False):
                note = "PENICILLIN - ANAPHYLAXIS (2019) - AMOXY-CLAV IV"
            alr.append((r["PAT_NO"], note, f"{R.randint(1, 28):02d}/{R.randint(1, 12):02d}/{p.allergy_year}"))
        elif R.random() < .5:
            alr.append((r["PAT_NO"], pick(["NKDA", "NO KNOWN ALLERGY", "NIL"]), r["REG_DT"]))
    pats = [(r["PAT_NO"], r["BRANCH_CD"], r["PAT_NM"], r["SEX"], r["DOB_TXT"], r["AGE_YRS"], r["PH_NO"], r["CITY"], r["REG_DT"])
            for r in legacy_pat.values()]
    if FILES_ONLY:
        for t, rows in (("pat_mstr", pats), ("visit_hdr", vis), ("alrgy_txt", alr), ("lab_rslt", lab), ("rx_line", rx), ("dis_summ", summ)):
            save_table(t, rows)
        return notes
    with psycopg.connect(PG, autocommit=True) as c:
        c.execute(DDL)
        cur = c.cursor()
        for t, rows in (("pat_mstr", pats), ("visit_hdr", vis), ("alrgy_txt", alr), ("lab_rslt", lab), ("rx_line", rx), ("dis_summ", summ)):
            save_table(t, rows)
            with cur.copy(f"COPY his.{t} FROM STDIN") as cp:
                for row in rows:
                    cp.write_row(row)
        # the read-only login Exasol uses: SELECT on his.*, nothing else
        c.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='his_reader') THEN "
                  "CREATE ROLE his_reader LOGIN; END IF; END $$;")
        c.execute(sql.SQL("ALTER ROLE his_reader PASSWORD {}").format(sql.Literal(hcconfig.secret("HC_PG_READER_PASSWORD"))))
        c.execute("GRANT USAGE ON SCHEMA his TO his_reader; GRANT SELECT ON ALL TABLES IN SCHEMA his TO his_reader;")
    print(f"postgres: {len(pats)} patients, {len(vis)} visits, {len(alr)} allergy notes, {len(rx)} rx lines, {len(summ)} summaries")
    return notes


# ----------------------------------------------------------------------------- write: MongoDB
def write_mongo(modern_pat, enc):
    pats, encs, notes = [], [], []
    for pid, r in modern_pat.items():
        p = r["person"]
        allergies = []
        # the modern EHR captured allergies at its OWN registration; a third of those it never heard about are missing
        if p.allergy and not getattr(p, "hero", False) and R.random() < .55:
            allergies.append({"substance": p.allergy[2], "reaction": p.allergy_reaction,
                              "severity": "severe" if p.allergy_reaction in ("anaphylaxis", "Stevens-Johnson syndrome", "angioedema") else "moderate",
                              "recorded": f"{max(p.allergy_year, r['registered'].year)}-{R.randint(1, 12):02d}-{R.randint(1, 28):02d}"})
        conditions = []
        for flag, code, disp in ((p.dm, "E11.9", "Type 2 diabetes mellitus"), (p.htn, "I10", "Essential hypertension"),
                                 (p.copd, "J44.9", "Chronic obstructive pulmonary disease"), (p.asthma, "J45.909", "Asthma"),
                                 (p.cad, "I25.10", "Coronary artery disease")):
            if flag:
                conditions.append({"code": code, "display": disp, "onset": str(R.randint(2005, 2023))})
        tel = p.mobile if R.random() < .9 or getattr(p, "hero", False) else f"00009{R.randint(100000000, 999999999) % 100000:05d}"   # a changed number
        pats.append({"_id": r["_id"], "mrn": r["mrn"], "name": {"given": r["given"], "family": r["family"], "text": f"{r['given']} {r['family']}"},
                     "gender": "female" if p.sex == "F" else "male", "birthDate": p.dob.isoformat(),
                     "telecom": {"mobile": f"+91 {tel}"}, "address": {"city": CITY[r["branch"]][0], "state": CITY[r["branch"]][1]},
                     "homeBranch": r["branch"], "registeredAt": r["registered"].isoformat(),
                     "allergies": allergies, "conditions": conditions})
    n = 0
    for e in enc:
        if e["system"] != "modern":
            continue
        p = e["person"]
        n += 1
        eid = f"ENC-{e['branch']}-{e['date']:%y%m}-{n:05d}"
        e["visit_id"] = eid
        rec_allergy = any(a for a in next(x for x in pats if x["_id"] == e["rec"])["allergies"]) if p.allergy else False
        meds = meds_for(e["cond"], p, rec_allergy)
        status = "completed"
        if e["current"]:
            status = "active"
        if e.get("hero_now"):
            meds, status = ["Amoxicillin-clavulanate", "Paracetamol", "Metformin"], "draft"
        e["meds"] = meds
        obs = []
        if e["cond"] in ("cap", "copd", "hf", "covid", "asthma"):
            obs.append({"code": "SpO2", "value": float(89 if e.get("hero_now") else R.randint(84, 97)), "unit": "%"})
        if p.dm:
            obs.append({"code": "HbA1c", "value": round(8.4 if e.get("hero_now") else R.uniform(6.6, 10.8), 1), "unit": "%"})
        obs.append({"code": "Temp", "value": round(38.6 if e.get("hero_now") else R.uniform(36.6, 39.4), 1), "unit": "C"})
        cls = "inpatient" if e["ip"] else ("emergency" if e["dept"] == "ER" else "outpatient")
        doc = {"_id": eid, "patientId": e["rec"], "branch": e["branch"], "class": cls, "department": DEPT[e["dept"]],
               "admitted": datetime.combine(e["date"], datetime.min.time()).replace(hour=R.randint(7, 22), minute=R.randint(0, 59)).isoformat(timespec="minutes"),
               "discharged": e["discharge"].isoformat() if e["discharge"] else None,
               "status": "in-progress" if e["current"] else "finished",
               "diagnosis": {"code": e["icd"], "display": e["disp"]},
               "medications": [{"name": m, "dose": DOSE.get(m, ""), "status": (status if m not in ("Paracetamol",) or status != "draft" else "active")} for m in meds],
               "observations": obs}
        if e["ip"]:
            txt = note_text(e["cond"], p, meds, None if e["current"] else e["los"], e["modality"], legacy=False)
            if e.get("hero_now"):
                txt = ("68-year-old woman, known diabetic and hypertensive. Presented with fever for 3 days, productive cough and "
                       "breathlessness. On examination crackles at the right lung base, SpO2 89% on room air, temperature 38.6 C. "
                       "Chest X-ray requested. Plan: admit, start amoxicillin-clavulanate, continue metformin. No known drug allergies "
                       "recorded at this site.")
            doc["note"] = txt
            notes.append(dict(NOTE_ID=f"M:{eid}", SOURCE="MODERN_EHR", RECORD_ID=e["rec"], ENCOUNTER_ID=eid, NOTE_TEXT=txt))
        encs.append(doc)
    if FILES_ONLY:
        save_collection("patients", pats)
        save_collection("encounters", encs)
        return notes
    cli = MongoClient(MONGO)
    db = cli["ehr"]
    db.drop_collection("patients")
    db.drop_collection("encounters")
    save_collection("patients", pats)
    save_collection("encounters", encs)
    db.patients.insert_many(pats)
    db.encounters.insert_many(encs)
    db.encounters.create_index("patientId")
    try:
        # created in admin (read on ehr only): the adapter authenticates against admin, as in the tested starter-kit setup
        cli["admin"].command("createUser", "ehr_reader", pwd=hcconfig.secret("HC_MONGO_READER_PASSWORD"), roles=[{"role": "read", "db": "ehr"}])
    except Exception as ex:  # noqa: BLE001 - already exists
        if "already exists" not in str(ex):
            raise
    cli.close()
    print(f"mongodb: {len(pats)} patients, {len(encs)} encounters, {sum(1 for d in encs if d['status'] == 'in-progress')} in a bed now")
    return notes


# ----------------------------------------------------------------------------- imaging plan (consumed by data/imaging.py)
def imaging_plan(enc):
    want = {"CXR": 120, "CT": 30, "MR": 18}
    plan = []
    hero_rows = [e for e in enc if e.get("hero_old") or e.get("hero_now")]
    pool = [e for e in enc if e["modality"] and not (e.get("hero_old") or e.get("hero_now"))]
    R.shuffle(pool)
    for e in hero_rows:
        plan.append(e)
    for m, k in want.items():
        plan += [e for e in pool if e["modality"] == m][: k - sum(1 for h in hero_rows if h["modality"] == m)]
    rows = []
    for i, e in enumerate(plan):
        p = e["person"]
        g, f = (p.given, p.family)
        rows.append(dict(SEQ=i, MODALITY_GROUP=e["modality"], PATIENT_ID_TAG=e["rec"].replace("/", ""),
                         PATIENT_NAME_TAG=f"{f.upper()}^{g.upper()}" if e["system"] == "modern" else f"{g.upper()}^{f[0]}",
                         BIRTH_DATE_TAG=p.dob.strftime("%Y%m%d"), SEX_TAG=p.sex, STUDY_DATE=e["date"].isoformat(),
                         INSTITUTION=f"Branch {e['branch'][-1]}", BRANCH=e["branch"], ENCOUNTER_ID=e["visit_id"],
                         CONDITION=e["cond"], HERO=("old" if e.get("hero_old") else "now" if e.get("hero_now") else ""),
                         TRUTH_PID=p.pid))
    with open(OUT / "imaging_plan.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"imaging plan: {len(rows)} studies ({sum(r['HERO'] != '' for r in rows)} for the hero)")


def main():
    people = make_people()
    h = hero(people)
    enc = make_encounters(people, h)
    legacy_pat, modern_pat, truth = build(people, h, enc)
    notes = write_pg(legacy_pat, enc) + write_mongo(modern_pat, enc)
    imaging_plan(enc)
    with open(OUT / "notes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["NOTE_ID", "SOURCE", "RECORD_ID", "ENCOUNTER_ID", "NOTE_TEXT"])
        w.writeheader()
        w.writerows(notes)
    with open(OUT / "truth_records.csv", "w", newline="") as f:
        csv.writer(f).writerows([("RECORD_ID", "SYSTEM", "TRUTH_PID")] + truth)
    # truth about allergy conflicts and readmissions, for checking the demo's numbers, never loaded
    conflicts = [(e["visit_id"], e["person"].pid, m) for e in enc if e["current"] and e["system"] == "modern" and e["person"].allergy
                 for m in e["meds"] if (e["person"].allergy[0] == "PENICILLIN" and m in ABX_PEN)
                 or (e["person"].allergy[0] == "NSAID" and m in ("Ibuprofen", "Diclofenac"))
                 or (e["person"].allergy[0] == "SULFONAMIDE" and m == "Co-trimoxazole")
                 or (e["person"].allergy[0] == "CEPHALOSPORIN" and m == "Ceftriaxone")]
    json.dump({"people": N_PEOPLE, "records": len(truth), "notes": len(notes), "current_conflicts": conflicts},
              open(OUT / "truth_summary.json", "w"), indent=1)
    print(f"truth: {len(truth)} records for {len({t[2] for t in truth})} people; {len(conflicts)} current allergy conflicts")


if __name__ == "__main__":
    main()
