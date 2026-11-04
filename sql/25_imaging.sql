-- The PACS on Amazon S3. The images stay as files; Exasol reads only the header index, in place, on every query.
-- CSV, not the Parquet copy beside it: on this Personal build the Parquet reader adds a fixed ~12 s to every request to an
-- amazonaws.com host (even for a missing file, with or without credentials); the CSV reader answers in 0.3 s.
-- The connection (a read-only IAM user) is created by setup/04_imaging.sh, which also fills in {{S3_PREFIX}} (HC_S3_PREFIX in
-- config.env; empty by default). Run this file through setup/04_imaging.sh, not on its own.
CREATE OR REPLACE VIEW HOSP_SRC.IMAGING_INDEX AS
SELECT * FROM (
  IMPORT INTO (PATIENT_ID VARCHAR(40), PATIENT_NAME VARCHAR(80), PATIENT_BIRTH_DATE VARCHAR(8), PATIENT_SEX VARCHAR(1),
               STUDY_INSTANCE_UID VARCHAR(80), SERIES_INSTANCE_UID VARCHAR(80), SOP_INSTANCE_UID VARCHAR(80),
               ACCESSION_NUMBER VARCHAR(20), MODALITY VARCHAR(4), BODY_PART VARCHAR(20), STUDY_DESCRIPTION VARCHAR(80),
               STUDY_DATE VARCHAR(8), INSTITUTION VARCHAR(40), REFERRING_PHYSICIAN VARCHAR(40), MANUFACTURER VARCHAR(60),
               ROWS_PX DECIMAL(6,0), COLS_PX DECIMAL(6,0), FILE_BYTES DECIMAL(12,0), S3_KEY VARCHAR(200), THUMB_KEY VARCHAR(120))
  FROM CSV AT HOSP_S3 FILE '{{S3_PREFIX}}index/dicom_index.csv');

-- Typed, and tied to a person through the master patient index (the PACS writes the local record id into PatientID).
CREATE OR REPLACE VIEW HOSP_CORE.IMAGING_STUDIES AS
SELECT m.UNIFIED_ID, i.PATIENT_ID AS PACS_PATIENT_ID, m.RECORD_ID, i.PATIENT_NAME AS NAME_IN_DICOM,
       TO_DATE(i.STUDY_DATE, 'YYYYMMDD') AS STUDY_DATE, i.MODALITY, i.BODY_PART, i.STUDY_DESCRIPTION,
       i.INSTITUTION, i.REFERRING_PHYSICIAN, i.ACCESSION_NUMBER, i.STUDY_INSTANCE_UID,
       '{{S3_PREFIX}}' || i.S3_KEY AS S3_KEY, '{{S3_PREFIX}}' || i.THUMB_KEY AS THUMB_KEY, i.FILE_BYTES
FROM HOSP_SRC.IMAGING_INDEX i
LEFT JOIN HOSP_CORE.MPI m ON m.PACS_PATIENT_ID = i.PATIENT_ID;
