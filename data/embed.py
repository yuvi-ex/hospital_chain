#!/usr/bin/env python3
"""Embed every clinical note (legacy discharge summaries + modern EHR notes) and store the VECTORS in Exasol.

The note text stays in its source system; Exasol keeps only the key and the vector:
  HOSP_CORE.NOTE_INDEX   (NOTE_ID, SOURCE_SYSTEM, RECORD_ID, ENCOUNTER_ID)     one row per note
  HOSP_CORE.NOTE_VECTORS (NOTE_ID, DIM, VAL)                            384 rows per note, L2-normalised
Long and narrow, so cosine similarity is a join + GROUP BY: no vector type, no UDF in the hot path.
Model: BAAI/bge-small-en-v1.5 (384-d) via fastembed, the same model the app uses for typed questions.
  .venv/bin/python data/embed.py              load the vectors shipped in data/out/note_vectors.parquet
  .venv/bin/python data/embed.py --compute    embed the notes again (downloads the model once), save, load
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
MODEL = "BAAI/bge-small-en-v1.5"
INDEX_FILE, VECTORS_FILE = OUT / "note_index.parquet", OUT / "note_vectors.parquet"


def compute():
    """notes.csv -> (NOTE_INDEX rows, NOTE_VECTORS rows), and save both as Parquet in data/out."""
    from fastembed import TextEmbedding
    notes = list(csv.DictReader(open(OUT / "notes.csv")))
    model = TextEmbedding(MODEL)
    vec = np.array(list(model.embed([n["NOTE_TEXT"].lower() for n in notes], batch_size=64)), dtype=np.float32)
    vec /= np.linalg.norm(vec, axis=1, keepdims=True)
    print(f"embedded {len(notes)} notes -> {vec.shape}", file=sys.stderr)
    idx = pd.DataFrame([{"NOTE_ID": n["NOTE_ID"], "SOURCE_SYSTEM": n["SOURCE"], "RECORD_ID": n["RECORD_ID"], "ENCOUNTER_ID": n["ENCOUNTER_ID"]} for n in notes])
    long = pd.DataFrame({"NOTE_ID": np.repeat(idx["NOTE_ID"].values, vec.shape[1]),
                         "DIM": np.tile(np.arange(vec.shape[1], dtype=np.int32), len(notes)),
                         "VAL": vec.reshape(-1).round(6)})
    idx.to_parquet(INDEX_FILE, index=False)
    long.to_parquet(VECTORS_FILE, index=False, compression="zstd")
    return idx, long


def main():
    if "--compute" in sys.argv or not VECTORS_FILE.exists():
        idx, long = compute()
    else:                       # the vectors shipped in the repository: same model, same notes, no model download
        idx, long = pd.read_parquet(INDEX_FILE), pd.read_parquet(VECTORS_FILE)
        print(f"read {len(idx)} notes, {len(long):,} vector rows from {VECTORS_FILE.name}", file=sys.stderr)
    con = hcconfig.exasol(compression=True)
    con.execute("CREATE SCHEMA IF NOT EXISTS HOSP_CORE")
    con.execute("CREATE OR REPLACE TABLE HOSP_CORE.NOTE_INDEX (NOTE_ID VARCHAR(40), SOURCE_SYSTEM VARCHAR(12), RECORD_ID VARCHAR(20), "
                "ENCOUNTER_ID VARCHAR(30), MODEL VARCHAR(40) DEFAULT 'bge-small-en-v1.5')")
    con.execute("CREATE OR REPLACE TABLE HOSP_CORE.NOTE_VECTORS (NOTE_ID VARCHAR(40), DIM DECIMAL(4,0), VAL DOUBLE)")
    con.import_from_pandas(idx, ("HOSP_CORE", "NOTE_INDEX"), import_params={"columns": ["NOTE_ID", "SOURCE_SYSTEM", "RECORD_ID", "ENCOUNTER_ID"]})
    con.import_from_pandas(long, ("HOSP_CORE", "NOTE_VECTORS"))
    n = con.execute("SELECT COUNT(*) FROM HOSP_CORE.NOTE_VECTORS").fetchval()
    print(f"loaded {len(idx)} notes, {n:,} vector rows into HOSP_CORE")


if __name__ == "__main__":
    main()
