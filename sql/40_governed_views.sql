-- HOSP_GOV: the governed semantic views:
-- definitions live in the view (COMMENT IS), rows are filtered by CURRENT_USER through ACCESS_MAP, and an AI client
-- connected through the Exasol MCP server as a named user can read these views and nothing else.
-- New here: PHI masking. PHI_LEVEL 'FULL' (treating clinician) sees identity; 'MASKED' (analyst) sees a pseudonym.
CREATE SCHEMA IF NOT EXISTS HOSP_GOV;

CREATE OR REPLACE TABLE HOSP_GOV.ACCESS_MAP (USER_NAME VARCHAR(128), BRANCH VARCHAR(3), PHI_LEVEL VARCHAR(6));
INSERT INTO HOSP_GOV.ACCESS_MAP VALUES
  ('SYS', '*', 'FULL'),                    -- the demo console
  ('HOSP_DR_BRB', 'BRB', 'FULL'),         -- treating physician, Branch B: own branch's patients, full history from every branch
  ('HOSP_QUALITY_ANALYST', '*', 'MASKED'); -- quality & readmissions analyst: every branch, no identities

-- One row per person, built from the native master patient index (fast, no source round trip).
CREATE OR REPLACE VIEW HOSP_CORE.PATIENT_SUMMARY AS
SELECT m.UNIFIED_ID,
       COALESCE(MAX(CASE WHEN r.SOURCE_SYSTEM = 'MODERN_EHR' THEN r.NAME_AS_RECORDED END),
                MAX(INITCAP(r.GIVEN_NAME) || ' ' || r.FAMILY_NAME)) AS PATIENT_NAME,
       MAX(r.SEX) AS SEX, MAX(r.BIRTH_DATE) AS BIRTH_DATE, MAX(r.MOBILE) AS MOBILE,
       COUNT(*) AS RECORDS, GROUP_CONCAT(DISTINCT r.SOURCE_SYSTEM ORDER BY r.SOURCE_SYSTEM SEPARATOR ' + ') AS SYSTEMS,
       GROUP_CONCAT(DISTINCT r.BRANCH ORDER BY r.BRANCH SEPARATOR ', ') AS BRANCHES,
       GROUP_CONCAT(r.RECORD_ID ORDER BY r.SOURCE_SYSTEM DESC SEPARATOR ', ') AS RECORD_IDS
FROM HOSP_CORE.MPI m JOIN HOSP_CORE.PATIENT_RECORDS r ON r.RECORD_ID = m.RECORD_ID
GROUP BY m.UNIFIED_ID;

-- Who may see whom: patients registered at one of the caller's branches ('*' = all). Not granted to anyone.
CREATE OR REPLACE VIEW HOSP_GOV.VISIBLE_PATIENTS AS
SELECT DISTINCT m.UNIFIED_ID, a.PHI_LEVEL
FROM HOSP_CORE.MPI m JOIN HOSP_CORE.PATIENT_RECORDS r ON r.RECORD_ID = m.RECORD_ID
JOIN HOSP_GOV.ACCESS_MAP a ON a.USER_NAME = CURRENT_USER AND (a.BRANCH = '*' OR a.BRANCH = r.BRANCH);

CREATE OR REPLACE VIEW HOSP_GOV.PATIENTS AS
SELECT p.UNIFIED_ID,
       CASE WHEN v.PHI_LEVEL = 'FULL' THEN p.PATIENT_NAME ELSE 'Patient ' || SUBSTR(HASH_SHA1(p.UNIFIED_ID), 1, 6) END AS PATIENT_NAME,
       p.SEX, CASE WHEN v.PHI_LEVEL = 'FULL' THEN p.BIRTH_DATE END AS BIRTH_DATE, YEAR(p.BIRTH_DATE) AS BIRTH_YEAR,
       YEARS_BETWEEN(DATE '2026-10-26', p.BIRTH_DATE) AS AGE   /* as of the data's date */, CASE WHEN v.PHI_LEVEL = 'FULL' THEN p.MOBILE END AS MOBILE,
       p.RECORDS, p.SYSTEMS, p.BRANCHES
FROM HOSP_CORE.PATIENT_SUMMARY p JOIN HOSP_GOV.VISIBLE_PATIENTS v ON v.UNIFIED_ID = p.UNIFIED_ID
COMMENT IS 'Governed data product. Grain: ONE ROW PER PERSON (UNIFIED_ID from the master patient index), however many records the branches hold. Rows are limited to the patients the caller may see; for a MASKED caller PATIENT_NAME is a pseudonym and BIRTH_DATE and MOBILE are NULL. SYSTEMS lists where this person has records (LEGACY_HIS = Branch A/Branch C HIS, MODERN_EHR = Branch B/Branch C EHR).';

CREATE OR REPLACE VIEW HOSP_GOV.ENCOUNTERS AS
SELECT e.UNIFIED_ID, e.ENCOUNTER_ID, e.SOURCE_SYSTEM, e.BRANCH, e.ENCOUNTER_CLASS, e.DEPARTMENT, e.ADMIT_DATE, e.DISCHARGE_DATE,
       e.LENGTH_OF_STAY, e.STATUS, e.DX_CODE, e.DIAGNOSIS
FROM HOSP_CORE.ENCOUNTERS e JOIN HOSP_GOV.VISIBLE_PATIENTS v ON v.UNIFIED_ID = e.UNIFIED_ID
COMMENT IS 'Grain: ONE ROW PER ENCOUNTER (visit or admission) from every branch system, read live. ENCOUNTER_CLASS = inpatient, outpatient or emergency. STATUS in-progress = the patient is in a bed now. LENGTH_OF_STAY is in days (NULL while admitted). Join to PATIENTS on UNIFIED_ID.';

CREATE OR REPLACE VIEW HOSP_GOV.READMISSIONS_30D AS
SELECT r.UNIFIED_ID, r.ENCOUNTER_ID, r.BRANCH, r.SOURCE_SYSTEM, r.ADMIT_DATE, r.DIAGNOSIS, r.PREV_BRANCH, r.PREV_DISCHARGE,
       r.DAYS_SINCE_DISCHARGE, r.VISIBLE_TO_ONE_SYSTEM
FROM HOSP_CORE.READMISSIONS_30D r JOIN HOSP_GOV.VISIBLE_PATIENTS v ON v.UNIFIED_ID = r.UNIFIED_ID
COMMENT IS 'Certified definition of a 30-day readmission: an inpatient admission within 0-30 days of the SAME PERSON''s previous inpatient discharge, at ANY branch, in ANY system. Grain: one row per readmission. VISIBLE_TO_ONE_SYSTEM = FALSE means the previous stay is under a different record id, so a single branch system cannot count it. Use this view for readmission rates; do not recompute from ENCOUNTERS.';

CREATE OR REPLACE VIEW HOSP_GOV.ALLERGY_ALERTS AS
SELECT c.UNIFIED_ID, p.PATIENT_NAME, c.ENCOUNTER_ID, c.PRESCRIBED_IN, c.DRUG, c.DOSE, c.ORDER_STATUS, c.DRUG_CLASS,
       c.ALLERGY_AS_RECORDED, c.SEVERITY, c.ALLERGY_RECORDED_IN, c.KNOWN_WHERE_PRESCRIBED
FROM HOSP_CORE.ALLERGY_CONFLICTS c JOIN HOSP_GOV.PATIENTS p ON p.UNIFIED_ID = c.UNIFIED_ID
COMMENT IS 'Certified safety check. Grain: one row per CURRENT medication order (draft or active) whose drug class matches an allergy recorded for the same person in ANY system. KNOWN_WHERE_PRESCRIBED = FALSE: the prescribing system holds no such allergy, so only the fused record reveals the conflict.';

CREATE OR REPLACE VIEW HOSP_GOV.IMAGING_STUDIES AS
SELECT i.UNIFIED_ID, i.STUDY_DATE, i.MODALITY, i.BODY_PART, i.STUDY_DESCRIPTION, i.INSTITUTION, i.ACCESSION_NUMBER, i.S3_KEY
FROM HOSP_CORE.IMAGING_STUDIES i JOIN HOSP_GOV.VISIBLE_PATIENTS v ON v.UNIFIED_ID = i.UNIFIED_ID
COMMENT IS 'Grain: ONE ROW PER IMAGING STUDY in the PACS on Amazon S3 (DICOM header index, read in place). MODALITY: DX/CR = X-ray, CT, MR = MRI. The images stay in S3 (S3_KEY); no pixels pass through the database.';

-- Read-only role for people and their AI agents: SELECT on the governed views, nothing else.
CREATE ROLE HOSP_AGENT_READER;   -- fails harmlessly if it already exists
GRANT SELECT ON HOSP_GOV.PATIENTS TO HOSP_AGENT_READER;
GRANT SELECT ON HOSP_GOV.ENCOUNTERS TO HOSP_AGENT_READER;
GRANT SELECT ON HOSP_GOV.READMISSIONS_30D TO HOSP_AGENT_READER;
GRANT SELECT ON HOSP_GOV.ALLERGY_ALERTS TO HOSP_AGENT_READER;
GRANT SELECT ON HOSP_GOV.IMAGING_STUDIES TO HOSP_AGENT_READER;
