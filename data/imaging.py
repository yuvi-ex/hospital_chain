#!/usr/bin/env python3
"""Build the imaging archive on S3 from REAL de-identified DICOM (The Cancer Imaging Archive, CC BY 4.0).

  chest X-ray + chest CT : COVID-19-AR    brain MRI : UPENN-GBM
One image per series is fetched from TCIA's public API, relabelled to a synthetic patient from
data/out/imaging_plan.csv (PatientID, name, birth date, study date, institution), downsampled to keep the
bucket small, and written as uncompressed DICOM. Then:

  s3://<bucket>/pacs/<branch>/<StudyInstanceUID>/<SOPInstanceUID>.dcm   the images (stay as files)
  s3://<bucket>/thumbs/<SOPInstanceUID>.png                              what the UI shows (via presigned URL)
  s3://<bucket>/index/dicom_index.parquet                                 the HEADERS, read back from the .dcm files

The index is derived from the DICOM headers with pydicom, the way a PACS export or an S3-event Lambda would
produce it. Exasol reads the CSV copy in place; it never touches pixels.

The repository already holds the result (data/out/dicom, thumbs, dicom_index.*), so a new set-up only uploads it:
  .venv/bin/python data/imaging.py upload     data/out -> your bucket (HC_S3_BUCKET, HC_S3_PREFIX, HC_AWS_PROFILE)
  .venv/bin/python data/imaging.py verify     every file is in the bucket, readable with the read-only key
  .venv/bin/python data/imaging.py build      redo it from TCIA (~1.8 GB of downloads; new UIDs), then upload
  .venv/bin/python data/imaging.py index      rebuild dicom_index.* from the DICOM headers in data/out/dicom
  .venv/bin/python data/imaging.py refresh    relabel the committed DICOM after generate.py changed the plan
"""
import csv
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import boto3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pydicom
from PIL import Image
from pydicom.pixels import apply_voi_lut
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "out"
RAW = ROOT / ".work" / "tcia"
DCM, THUMB = OUT / "dicom", OUT / "thumbs"
for d in (RAW, DCM, THUMB):
    d.mkdir(parents=True, exist_ok=True)
API = "https://services.cancerimagingarchive.net/nbia-api/services/v1"
BUCKET, REGION = C.S3_BUCKET, C.S3_REGION
DESC = {"CXR": ("XR CHEST PA", "CHEST"), "CT": ("CT CHEST WITHOUT CONTRAST", "CHEST"), "MR": ("MRI BRAIN WITH AND WITHOUT CONTRAST", "BRAIN")}
DOCTORS = {"BRA": ["RAMAN^K", "PRABHU^S", "IYER^V"], "BRB": ["Rao^Anitha", "Shetty^Kiran", "Menon^Divya"],
           "BRC": ["REDDY^P", "Khan^Imran", "NAIDU^S"]}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def series_pool():
    """Deterministic list of candidate series per modality group."""
    f = RAW / "series.json"
    if f.exists():
        return json.loads(f.read_text())
    ar = json.loads(get(f"{API}/getSeries?Collection=COVID-19-AR"))
    gbm = json.loads(get(f"{API}/getSeries?Collection=UPENN-GBM"))
    pool = {"CXR": sorted([s["SeriesInstanceUID"] for s in ar if s["Modality"] in ("DX", "CR") and s.get("BodyPartExamined") == "CHEST"]),
            "CT": sorted([s["SeriesInstanceUID"] for s in ar if s["Modality"] == "CT" and s.get("BodyPartExamined") in ("CHEST", "THORAX")]),
            "MR": sorted([s["SeriesInstanceUID"] for s in gbm if s["Modality"] == "MR" and "T1" in (s.get("SeriesDescription") or "").upper()
                          and "GD" in (s.get("SeriesDescription") or "").upper()])}
    if len(pool["MR"]) < 30:
        pool["MR"] = sorted([s["SeriesInstanceUID"] for s in gbm if s["Modality"] == "MR"])
    f.write_text(json.dumps(pool))
    return pool


def fetch(series_uid):
    """One SOP instance from the middle of the series, cached."""
    f = RAW / f"{hashlib.sha1(series_uid.encode()).hexdigest()[:16]}.dcm"
    if f.exists() and f.stat().st_size > 0:
        return f
    sops = json.loads(get(f"{API}/getSOPInstanceUIDs?SeriesInstanceUID={series_uid}"))
    uids = sorted(s["SOPInstanceUID"] for s in sops)
    sop = uids[len(uids) // 2]
    f.write_bytes(get(f"{API}/getSingleImage?SeriesInstanceUID={series_uid}&SOPInstanceUID={sop}"))
    return f


def display_array(ds):
    arr = ds.pixel_array
    if arr.ndim == 3:
        arr = arr[arr.shape[0] // 2]
    try:
        arr = apply_voi_lut(arr, ds)
    except Exception:  # noqa: BLE001
        pass
    arr = arr.astype(np.float32)
    lo, hi = np.percentile(arr, (0.5, 99.5))
    arr = np.clip((arr - lo) / max(hi - lo, 1), 0, 1)
    if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
        arr = 1 - arr
    return arr


# Patient-level facts of the SOURCE subject that do not belong to the synthetic patient: removed, never carried over.
SOURCE_ONLY = ("PatientWeight", "PatientSize", "EthnicGroup", "PatientComments", "AdditionalPatientHistory", "OtherPatientIDs",
               "OtherPatientIDsSequence", "OtherPatientNames", "PatientAddress", "PatientTelephoneNumbers", "PatientMotherBirthName",
               "MilitaryRank", "BranchOfService", "Occupation", "PregnancyStatus", "SmokingStatus", "MedicalAlerts", "Allergies",
               "ClinicalTrialSponsorName", "ClinicalTrialProtocolID", "ClinicalTrialProtocolName", "ClinicalTrialSiteID",
               "ClinicalTrialSiteName", "ClinicalTrialSubjectID", "ClinicalTrialSubjectReadingID", "ClinicalTrialTimePointID",
               "ClinicalTrialTimePointDescription", "ClinicalTrialCoordinatingCenterName", "ClinicalTrialSeriesID",
               "ClinicalTrialSeriesDescription", "DeidentificationMethodCodeSequence", "LongitudinalTemporalInformationModified",
               "IssuerOfPatientID", "InstitutionAddress", "InstitutionalDepartmentName", "StationName", "PerformingPhysicianName",
               "OperatorsName", "PhysiciansOfRecord", "NameOfPhysiciansReadingStudy", "RequestingPhysician", "StudyID")
STANDARD_UID = "1.2.840.10008."          # DICOM's own class / syntax UIDs: kept; every other UID is replaced


def relabel_header(ds, plan, n):
    """Make every header field belong to the synthetic patient of `plan`. Returns (branch, study, series, sop) UIDs.

    TCIA already de-identified the source images. This goes further so nothing of the source subject or collection
    remains: private tags, every date and time, every non-standard UID (also inside sequences) and the source subject's
    age, size, weight and ethnicity are replaced or removed."""
    seed = f"hc-{plan['SEQ']}-{plan['ENCOUNTER_ID']}"
    study, series, sop = (generate_uid(entropy_srcs=[seed, k]) for k in ("study", "series", "sop"))
    desc, part = DESC[plan["MODALITY_GROUP"]]
    d = plan["STUDY_DATE"].replace("-", "")
    t = f"{9 + n % 9:02d}{(n * 7) % 60:02d}00"
    br = plan["BRANCH"]
    ds.remove_private_tags()                                # e.g. the source collection's name
    for kw in SOURCE_ONLY:
        if kw in ds:
            delattr(ds, kw)
    for el in ds.iterall():                                 # every date/time, also inside sequences, becomes the study's
        if el.VR == "DA" and el.value:
            el.value = d
        elif el.VR == "TM" and el.value:
            el.value = t
        elif el.VR == "DT" and el.value:
            el.value = d + t
        elif el.VR == "UI" and el.value and not str(el.value).startswith(STANDARD_UID):
            el.value = generate_uid(entropy_srcs=[seed, str(el.value)])   # same old UID -> same new UID within a study
    # keep the pixel data and the scanner description; replace every patient/study identifier
    ds.PatientID, ds.PatientName = plan["PATIENT_ID_TAG"], plan["PATIENT_NAME_TAG"]
    ds.PatientBirthDate, ds.PatientSex = plan["BIRTH_DATE_TAG"], plan["SEX_TAG"]
    b = plan["BIRTH_DATE_TAG"]
    ds.PatientAge = f"{int(d[:4]) - int(b[:4]) - (d[4:] < b[4:]):03d}Y"     # from the synthetic birth date
    ds.StudyDate = ds.SeriesDate = ds.ContentDate = ds.AcquisitionDate = d
    ds.StudyTime = ds.SeriesTime = t
    ds.InstitutionName, ds.StudyDescription, ds.BodyPartExamined = plan["INSTITUTION"], desc, part
    ds.AccessionNumber = f"{br}{d[2:]}{plan['SEQ']:04d}"
    ds.ReferringPhysicianName = DOCTORS[br][n % 3]
    ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.SOPInstanceUID = study, series, sop
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "TCIA de-identified; relabelled synthetic patient; downsampled"   # LO: max 64
    return br, study, series, sop


def refresh():
    """Relabel the committed DICOM in place against the current imaging_plan.csv (no download, pixels untouched).

    Use after data/generate.py changed the plan (IDs, branches). Each file is matched to its plan row by the SEQ in its
    accession number; its preview is renamed with it, and the header index is rebuilt."""
    plan = list(csv.DictReader(open(OUT / "imaging_plan.csv")))
    for p in plan:
        p["SEQ"] = int(p["SEQ"])
    by_seq = {p["SEQ"]: (n, p) for n, p in enumerate(plan)}
    old = written()
    assert len(old) == len(plan), f"{len(old)} files for {len(plan)} planned studies"
    done = []
    for path in old:
        ds = pydicom.dcmread(path)
        n, p = by_seq[int(str(ds.AccessionNumber)[-4:])]
        old_sop = str(ds.SOPInstanceUID)
        br, study, _, sop = relabel_header(ds, p, n)
        dst = DCM / br / study / f"{sop}.dcm"
        dst.parent.mkdir(parents=True, exist_ok=True)
        ds.save_as(dst, enforce_file_format=True)
        if dst != path:
            path.unlink()
        if (THUMB / f"{old_sop}.png").exists() and old_sop != sop:
            (THUMB / f"{old_sop}.png").rename(THUMB / f"{sop}.png")
        done.append(dst)
    for d in sorted(DCM.glob("*/*"), reverse=True):      # folders left empty by the move
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    for d in DCM.glob("*"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print(f"relabelled {len(done)} files")
    index()


def relabel(src, plan, n):
    ds = pydicom.dcmread(src)
    arr = display_array(ds)
    img = Image.fromarray((arr * 65535).astype(np.uint16))      # 16-bit greyscale (Pillow infers I;16)
    img.thumbnail((768, 768))
    small = np.asarray(img, dtype=np.uint16) >> 4            # 12-bit, stored in 16
    br, study, series, sop = relabel_header(ds, plan, n)
    for tag in ("NumberOfFrames", "PerFrameFunctionalGroupsSequence", "SharedFunctionalGroupsSequence"):
        if tag in ds:
            delattr(ds, tag)
    ds.Rows, ds.Columns = small.shape
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    for tag in ("WindowCenter", "WindowWidth", "VOILUTSequence", "ModalityLUTSequence", "RescaleIntercept", "RescaleSlope", "LossyImageCompression"):
        if tag in ds:
            delattr(ds, tag)
    ds.WindowCenter, ds.WindowWidth = 2048, 4096
    ds.PixelData = small.tobytes()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dst = DCM / br / study / f"{sop}.dcm"
    dst.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(dst, enforce_file_format=True)
    th = Image.fromarray((arr * 255).astype(np.uint8))
    th.thumbnail((420, 420))
    th.save(THUMB / f"{sop}.png", optimize=True)
    return dst


def index_row(path):
    """Read back what was written: the index is the headers, nothing invented."""
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    br = path.parts[-3]
    return {"PATIENT_ID": str(ds.PatientID), "PATIENT_NAME": str(ds.PatientName), "PATIENT_BIRTH_DATE": str(ds.PatientBirthDate),
            "PATIENT_SEX": str(ds.PatientSex), "STUDY_INSTANCE_UID": str(ds.StudyInstanceUID), "SERIES_INSTANCE_UID": str(ds.SeriesInstanceUID),
            "SOP_INSTANCE_UID": str(ds.SOPInstanceUID), "ACCESSION_NUMBER": str(ds.AccessionNumber), "MODALITY": str(ds.Modality),
            "BODY_PART": str(ds.BodyPartExamined), "STUDY_DESCRIPTION": str(ds.StudyDescription), "STUDY_DATE": str(ds.StudyDate),
            "INSTITUTION": str(ds.InstitutionName), "REFERRING_PHYSICIAN": str(ds.ReferringPhysicianName),
            "MANUFACTURER": str(getattr(ds, "Manufacturer", "")), "ROWS_PX": int(ds.Rows), "COLS_PX": int(ds.Columns),
            "FILE_BYTES": path.stat().st_size,
            "S3_KEY": f"pacs/{br}/{ds.StudyInstanceUID}/{ds.SOPInstanceUID}.dcm", "THUMB_KEY": f"thumbs/{ds.SOPInstanceUID}.png"}


def build():
    """TCIA -> relabelled DICOM + previews in data/out (slow: ~1.8 GB of downloads). The repository already holds the result."""
    plan = list(csv.DictReader(open(OUT / "imaging_plan.csv")))
    for p in plan:
        p["SEQ"] = int(p["SEQ"])
    pool = series_pool()
    print({k: len(v) for k, v in pool.items()})
    used = {k: 0 for k in pool}
    for n, p in enumerate(plan):
        g = p["MODALITY_GROUP"]
        for _ in range(6):                  # skip a series that will not decode
            uid = pool[g][(used[g] * 7919) % len(pool[g])]
            used[g] += 1
            try:
                relabel(fetch(uid), p, n)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  skip {g} {uid[-12:]}: {str(e)[:90]}", file=sys.stderr)
        if n % 20 == 0:
            print(f"  {n + 1}/{len(plan)}", flush=True)
    index()


def written():
    return sorted(DCM.glob("*/*/*.dcm"))


def index():
    """The header index, read back from the DICOM files in data/out/dicom: what Exasol reads in place on S3."""
    rows = [index_row(p) for p in written()]
    schema = pa.schema([(k, pa.int64() if k in ("ROWS_PX", "COLS_PX", "FILE_BYTES") else pa.string()) for k in rows[0]])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), OUT / "dicom_index.parquet")
    import pyarrow.csv as pc   # the copy Exasol reads live (see sql/25_imaging.sql for why CSV)
    pc.write_csv(pa.Table.from_pylist(rows, schema=schema), OUT / "dicom_index.csv", pc.WriteOptions(include_header=False))
    print(f"index: {len(rows)} studies, {sum(r['FILE_BYTES'] for r in rows) / 1e6:.0f} MB of DICOM")
    return rows


def objects():
    """(local file, S3 key, content type) for everything the archive holds, keys under HC_S3_PREFIX."""
    pre = C.S3_PREFIX
    out = [(p, f"{pre}pacs/{p.parts[-3]}/{p.parts[-2]}/{p.name}", "application/dicom") for p in written()]
    out += [(t, f"{pre}thumbs/{t.name}", "image/png") for t in sorted(THUMB.glob("*.png"))]
    out += [(OUT / f, f"{pre}index/{f}", ct) for f, ct in (("dicom_index.parquet", "application/octet-stream"), ("dicom_index.csv", "text/csv"))]
    return out


def s3(admin=True):
    if admin:
        return boto3.Session(profile_name=C.AWS_PROFILE, region_name=REGION).client("s3")
    k = json.loads(C.S3_KEY_FILE.read_text())["AccessKey"]          # the read-only key, as Exasol and the console use it
    return boto3.client("s3", region_name=REGION, aws_access_key_id=k["AccessKeyId"], aws_secret_access_key=k["SecretAccessKey"])


def upload():
    """data/out -> s3://HC_S3_BUCKET/HC_S3_PREFIX{pacs,thumbs,index}/ with the admin profile (HC_AWS_PROFILE)."""
    cli = s3()
    objs = objects()
    for i, (path, key, ct) in enumerate(objs):
        cli.upload_file(str(path), BUCKET, key, ExtraArgs={"ContentType": ct})
        if i % 50 == 0:
            print(f"  {i + 1}/{len(objs)}", flush=True)
    print(f"uploaded {len(objs)} files to s3://{BUCKET}/{C.S3_PREFIX}")


def verify():
    """Every local file is in the bucket with the same size, readable with the READ-ONLY key. Writes nothing."""
    cli = s3(admin=False)
    objs, bad = objects(), []
    for path, key, _ in objs:
        try:
            if cli.head_object(Bucket=BUCKET, Key=key)["ContentLength"] != path.stat().st_size:
                bad.append(f"size differs: {key}")
        except Exception as e:  # noqa: BLE001
            bad.append(f"{key}: {str(e)[:80]}")
    print(f"verify: {len(objs) - len(bad)}/{len(objs)} objects match in s3://{BUCKET}/{C.S3_PREFIX}")
    for b in bad[:10]:
        print("  " + b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("build", "refresh", "index", "upload", "verify"):
        sys.exit(__doc__)
    {"build": build, "refresh": refresh, "index": index, "upload": upload, "verify": verify}[cmd]()
