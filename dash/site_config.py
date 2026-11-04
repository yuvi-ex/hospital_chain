"""Where the console finds the repository, the S3 bucket and the read-only key.

In a checkout this reads config.env through hcconfig.py. dash-server runs the app from its own copy of these files, outside
the repository, so dash/deploy.py uploads a frozen version of this module with the values filled in.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig as _C  # noqa: E402

ROOT, BUCKET, REGION, KEYFILE, PY = _C.ROOT, _C.S3_BUCKET, _C.S3_REGION, _C.S3_KEY_FILE, _C.PY
