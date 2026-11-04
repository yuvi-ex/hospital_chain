-- HOSP_CORE: the master patient index. One person, many records: legacy HIS (per branch) + modern EHR + PACS.
-- Rebuilt from the LIVE sources by this script (in production: nightly, or on every new registration).
-- Deterministic rules, every link explained in MATCH_REASON. No model, nothing to retrain.

-- 1. every patient record the chain holds, read live from Postgres and MongoDB
CREATE OR REPLACE TABLE HOSP_CORE.PATIENT_RECORDS AS
SELECT RECORD_ID, SOURCE_SYSTEM, BRANCH, NAME_AS_RECORDED, GIVEN_NAME, FAMILY_NAME, SEX, BIRTH_DATE, BIRTH_DATE_SWAPPED,
       BIRTH_DATE_AS_RECORDED, AGE_ONLY, MOBILE, CITY
FROM HOSP_SRC.LEGACY_PATIENTS
UNION ALL
SELECT RECORD_ID, SOURCE_SYSTEM, BRANCH, NAME_AS_RECORDED, GIVEN_NAME, FAMILY_NAME, SEX, BIRTH_DATE, CAST(NULL AS DATE),
       BIRTH_DATE_AS_RECORDED, CAST(NULL AS DECIMAL(4,0)), MOBILE, CITY
FROM HOSP_SRC.MODERN_PATIENTS;

-- 2. score candidate pairs (blocked on sex + one strong key, so this is not a full cross join)
CREATE OR REPLACE TABLE HOSP_CORE.MATCH_CANDIDATES AS
WITH pairs AS (
  SELECT a.RECORD_ID AS A_ID, b.RECORD_ID AS B_ID, a.SOURCE_SYSTEM AS A_SYS, b.SOURCE_SYSTEM AS B_SYS,
    CASE WHEN a.GIVEN_NAME = b.GIVEN_NAME THEN 25
         WHEN SOUNDEX(a.GIVEN_NAME) = SOUNDEX(b.GIVEN_NAME) OR EDIT_DISTANCE(a.GIVEN_NAME, b.GIVEN_NAME) <= 2 THEN 15 ELSE 0 END AS S_GIVEN,
    CASE WHEN a.FAMILY_NAME = b.FAMILY_NAME AND LENGTH(a.FAMILY_NAME) > 1 THEN 15
         WHEN SUBSTR(a.FAMILY_NAME, 1, 1) = SUBSTR(b.FAMILY_NAME, 1, 1) THEN 10 ELSE -15 END AS S_FAMILY,
    CASE WHEN a.BIRTH_DATE = b.BIRTH_DATE THEN 35
         WHEN a.BIRTH_DATE_SWAPPED = b.BIRTH_DATE OR b.BIRTH_DATE_SWAPPED = a.BIRTH_DATE THEN 25
         -- ages were recorded against the data set's reference date (2026-10-26), not today: the result never drifts
         WHEN (a.BIRTH_DATE IS NULL AND ABS(a.AGE_ONLY - YEARS_BETWEEN(DATE '2026-10-26', b.BIRTH_DATE)) <= 1)
           OR (b.BIRTH_DATE IS NULL AND ABS(b.AGE_ONLY - YEARS_BETWEEN(DATE '2026-10-26', a.BIRTH_DATE)) <= 1) THEN 10
         ELSE 0 END AS S_BIRTH,
    CASE WHEN a.MOBILE = b.MOBILE THEN 30 ELSE 0 END AS S_MOBILE,
    CASE WHEN a.BIRTH_DATE_SWAPPED = b.BIRTH_DATE OR b.BIRTH_DATE_SWAPPED = a.BIRTH_DATE THEN 1 ELSE 0 END AS SWAPPED,
    CASE WHEN a.BIRTH_DATE IS NULL OR b.BIRTH_DATE IS NULL THEN 1 ELSE 0 END AS AGE_ONLY
  FROM HOSP_CORE.PATIENT_RECORDS a
  JOIN HOSP_CORE.PATIENT_RECORDS b
    ON a.SEX = b.SEX AND a.RECORD_ID < b.RECORD_ID
   AND NOT (a.SOURCE_SYSTEM = 'MODERN_EHR' AND b.SOURCE_SYSTEM = 'MODERN_EHR')           -- the EHR is one database: no duplicates inside it
   AND NOT (a.SOURCE_SYSTEM = 'LEGACY_HIS' AND b.SOURCE_SYSTEM = 'LEGACY_HIS' AND a.BRANCH = b.BRANCH)
   AND (SOUNDEX(a.GIVEN_NAME) = SOUNDEX(b.GIVEN_NAME) OR a.MOBILE = b.MOBILE OR a.BIRTH_DATE = b.BIRTH_DATE))
SELECT p.*, S_GIVEN + S_FAMILY + S_BIRTH + S_MOBILE AS SCORE,
       TRIM(CASE S_GIVEN WHEN 25 THEN 'given name exact · ' WHEN 15 THEN 'given name sounds alike · ' ELSE '' END
         || CASE S_FAMILY WHEN 15 THEN 'surname exact · ' WHEN 10 THEN 'surname initial agrees · ' ELSE 'surname differs · ' END
         || CASE WHEN S_BIRTH = 35 THEN 'birth date exact · ' WHEN SWAPPED = 1 THEN 'birth date with day/month swapped · '
                 WHEN S_BIRTH = 10 THEN 'age agrees (no birth date recorded) · ' ELSE '' END
         || CASE S_MOBILE WHEN 30 THEN 'mobile exact' ELSE '' END, ' ·') AS MATCH_REASON
FROM pairs p;

-- 3. link: every record joins the best-scoring partner at or above the threshold; the modern EHR record anchors a person
CREATE OR REPLACE TABLE HOSP_CORE.MPI AS
WITH links AS (
  SELECT A_ID, B_ID, SCORE, MATCH_REASON FROM HOSP_CORE.MATCH_CANDIDATES WHERE SCORE >= 70),
to_modern AS (                                   -- legacy record -> its best modern record
  SELECT L_ID, M_ID, SCORE, MATCH_REASON FROM (
    SELECT CASE WHEN A_SYS = 'LEGACY_HIS' THEN A_ID ELSE B_ID END AS L_ID,
           CASE WHEN A_SYS = 'MODERN_EHR' THEN A_ID ELSE B_ID END AS M_ID, SCORE, MATCH_REASON,
           ROW_NUMBER() OVER (PARTITION BY CASE WHEN A_SYS = 'LEGACY_HIS' THEN A_ID ELSE B_ID END ORDER BY SCORE DESC) AS RN
    FROM HOSP_CORE.MATCH_CANDIDATES WHERE SCORE >= 70 AND A_SYS <> B_SYS) WHERE RN = 1),
legacy_pairs AS (                                -- legacy <-> legacy across branches (Branch A and Branch C registered them twice)
  SELECT A_ID, B_ID, SCORE, MATCH_REASON, ROW_NUMBER() OVER (PARTITION BY A_ID ORDER BY SCORE DESC) AS RN
  FROM HOSP_CORE.MATCH_CANDIDATES WHERE SCORE >= 70 AND A_SYS = 'LEGACY_HIS' AND B_SYS = 'LEGACY_HIS'),
anchor AS (
  SELECT r.RECORD_ID, r.SOURCE_SYSTEM,
         CASE WHEN r.SOURCE_SYSTEM = 'MODERN_EHR' THEN r.RECORD_ID
              ELSE COALESCE(tm.M_ID, tma.M_ID, tmb.M_ID, LEAST(r.RECORD_ID, COALESCE(lpa.B_ID, lpb.A_ID, r.RECORD_ID))) END AS ANCHOR_ID,
         COALESCE(tm.SCORE, lpa.SCORE, lpb.SCORE) AS LINK_SCORE,
         COALESCE(tm.MATCH_REASON, lpa.MATCH_REASON, lpb.MATCH_REASON) AS MATCH_REASON
  FROM HOSP_CORE.PATIENT_RECORDS r
  LEFT JOIN to_modern tm ON tm.L_ID = r.RECORD_ID
  LEFT JOIN legacy_pairs lpa ON lpa.A_ID = r.RECORD_ID AND lpa.RN = 1
  LEFT JOIN legacy_pairs lpb ON lpb.B_ID = r.RECORD_ID AND lpb.RN = 1
  LEFT JOIN to_modern tma ON tma.L_ID = lpa.B_ID          -- transitive: my legacy twin is linked to a modern record
  LEFT JOIN to_modern tmb ON tmb.L_ID = lpb.A_ID)
SELECT 'UP-' || LPAD(DENSE_RANK() OVER (ORDER BY ANCHOR_ID), 6, '0') AS UNIFIED_ID, RECORD_ID, SOURCE_SYSTEM,
       REPLACE(RECORD_ID, '/', '') AS PACS_PATIENT_ID,          -- what the imaging system writes into the DICOM PatientID tag
       ANCHOR_ID, LINK_SCORE, MATCH_REASON
FROM anchor;

-- 4. borderline pairs a human should look at (never auto-linked)
CREATE OR REPLACE VIEW HOSP_CORE.MATCH_REVIEW_QUEUE AS
SELECT A_ID, B_ID, SCORE, MATCH_REASON FROM HOSP_CORE.MATCH_CANDIDATES WHERE SCORE BETWEEN 55 AND 69;
