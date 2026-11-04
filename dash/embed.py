"""Typed text -> the same 384-d model the notes were embedded with -> a VALUES list the similarity SQL joins on.

fastembed (and its ONNX runtime) lives in the project venv, not in the shared dash-server venv, so the text is embedded
in a short-lived subprocess of the project's .venv. Repeated texts are answered from memory.
Run directly (python embed.py "some text") it prints the vector as JSON.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import site_config as S  # noqa: E402

PY = Path(S.PY)
_SEEN = {}


def _vector(text):
    out = subprocess.run([str(PY), str(Path(__file__).resolve()), text], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "embedding failed")
    return json.loads(out.stdout)


def values_sql(text):
    """Returns (SELECT DIM, VAL FROM VALUES ..., seconds spent embedding)."""
    t = time.time()
    key = text.strip().lower()
    if key not in _SEEN:
        _SEEN[key] = _vector(key)
    rows = ", ".join(f"({i}, {x:.6f})" for i, x in enumerate(_SEEN[key]))
    return f"SELECT DIM, VAL FROM VALUES {rows} AS t(DIM, VAL)", time.time() - t


if __name__ == "__main__":
    import numpy as np
    from fastembed import TextEmbedding
    v = np.array(list(TextEmbedding("BAAI/bge-small-en-v1.5").embed([sys.argv[1].lower()]))[0], dtype=np.float64)
    v /= np.linalg.norm(v)
    print(json.dumps([round(float(x), 6) for x in v]))
