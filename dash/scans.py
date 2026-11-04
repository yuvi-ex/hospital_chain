"""The PACS on S3: signed links for one file, and the image rendered live from its DICOM file, step by step.

The database never touches pixels. Exasol returns the S3 key of each study (from the header index it reads in place);
this console signs a 15-minute GET for that key with the read-only IAM user Exasol itself uses, and the browser
downloads the preview from S3. "Render from the DICOM file" repeats the whole path for the original file: sign,
download, parse the header, apply the window from the header, encode a PNG, and times each step.
"""
import base64
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import site_config as S  # noqa: E402

KEYFILE = Path(S.KEYFILE)     # created by setup/s3_reader.sh, mode 600; read here, never shown
BUCKET, REGION = S.BUCKET, S.REGION
EXPIRES = 900
_CLIENT = {}


def client():
    if "s3" not in _CLIENT:
        import boto3
        from botocore.config import Config
        # regional endpoint + SigV4: the global endpoint signs for us-east-1 and S3 answers SignatureDoesNotMatch
        cfg = dict(region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com",
                   config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
        k = json.loads(KEYFILE.read_text())["AccessKey"]
        _CLIENT["s3"] = boto3.client("s3", aws_access_key_id=k["AccessKeyId"], aws_secret_access_key=k["SecretAccessKey"], **cfg)
    return _CLIENT["s3"]


def signed(key, secs=EXPIRES):
    try:
        return client().generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=secs)
    except Exception:  # noqa: BLE001
        return ""


def links(key):
    """Every way to point at this one object."""
    return {"uri": f"s3://{BUCKET}/{key}",
            "https": f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}",
            "console": (f"https://{REGION}.console.aws.amazon.com/s3/object/{BUCKET}?region={REGION}&bucketType=general"
                        f"&prefix={urllib.parse.quote(key, safe='')}")}


def render(key):
    """Download the DICOM file from S3 and render it here. Returns {steps, img, tags} or {error}."""
    steps = []

    def step(name, detail, t0):
        steps.append({"name": name, "detail": detail, "secs": time.time() - t0})

    try:
        t = time.time()
        url = signed(key)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        step("Sign a GET for this one file", f"SigV4, {REGION}, expires in {int(q.get('X-Amz-Expires', [EXPIRES])[0]) // 60} min, "
             "signed by hc-s3-reader (GetObject + ListBucket on this bucket only)", t)

        t = time.time()
        with urllib.request.urlopen(url, timeout=30) as r:
            raw = r.read()
            etype = r.headers.get("Content-Type", "")
        step("Download the DICOM file from S3", f"{len(raw) / 1024:,.0f} KB, {etype or 'application/octet-stream'}, straight from S3 to this console", t)

        t = time.time()
        import numpy as np
        import pydicom
        ds = pydicom.dcmread(io.BytesIO(raw))
        tags = {"PatientID": str(ds.get("PatientID", "")), "PatientName": str(ds.get("PatientName", "")),
                "Modality": str(ds.get("Modality", "")), "StudyDate": str(ds.get("StudyDate", "")),
                "Institution": str(ds.get("InstitutionName", "")), "Size": f"{ds.Rows} x {ds.Columns} px",
                "Bits": f"{ds.BitsStored} of {ds.BitsAllocated}", "Photometric": str(ds.get("PhotometricInterpretation", "")),
                "Window": f"centre {ds.get('WindowCenter', '?')}, width {ds.get('WindowWidth', '?')}",
                "TransferSyntax": str(ds.file_meta.TransferSyntaxUID.name)}
        step("Parse the DICOM header", f"{tags['Modality']} {tags['Size']}, {tags['Bits']} bits, PatientID {tags['PatientID']}", t)

        t = time.time()
        arr = ds.pixel_array.astype(np.float32)
        if arr.ndim == 3:
            arr = arr[arr.shape[0] // 2]
        c, w = float(ds.get("WindowCenter", arr.mean())), float(ds.get("WindowWidth", arr.max() - arr.min() or 1))
        lo, hi = c - w / 2, c + w / 2
        if arr.max() < lo + (hi - lo) * 0.25:          # header window far wider than the pixels: fall back to the 0.5/99.5 percentiles
            lo, hi = np.percentile(arr, (0.5, 99.5))
        img = np.clip((arr - lo) / max(hi - lo, 1), 0, 1)
        if tags["Photometric"] == "MONOCHROME1":
            img = 1 - img
        step("Apply the window to the pixel data", f"{arr.size / 1e6:.2f} M pixels mapped from {tags['Bits']} bits to 8-bit grey", t)

        t = time.time()
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray((img * 255).astype(np.uint8)).save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
        step("Encode a PNG for the browser", f"{len(png) / 1024:,.0f} KB", t)
        return {"steps": steps, "img": "data:image/png;base64," + base64.b64encode(png).decode(), "tags": tags}
    except Exception as e:  # noqa: BLE001
        return {"steps": steps, "error": str(e)[:300]}
