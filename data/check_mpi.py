#!/usr/bin/env python3
"""Score HOSP_CORE.MPI against the generator's ground truth (data/out/truth_records.csv, never loaded into Exasol).
Pairwise: a pair of records is 'linked' if they share a UNIFIED_ID, 'true' if they share a TRUTH_PID."""
import csv
import itertools
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
con = hcconfig.exasol()
mpi = dict(con.execute("SELECT RECORD_ID, UNIFIED_ID FROM HOSP_CORE.MPI").fetchall())
truth = {r["RECORD_ID"]: r["TRUTH_PID"] for r in csv.DictReader(open(OUT / "truth_records.csv"))}


def pairs(groups):
    out = set()
    for g in groups.values():
        out |= {tuple(sorted(p)) for p in itertools.combinations(g, 2)}
    return out


by_u, by_t = defaultdict(list), defaultdict(list)
for r, u in mpi.items():
    by_u[u].append(r)
for r, t in truth.items():
    by_t[t].append(r)
linked, true = pairs(by_u), pairs(by_t)
tp = len(linked & true)
print(f"records {len(mpi)}  people (truth) {len(by_t)}  unified ids {len(by_u)}")
print(f"pairs linked {len(linked)}  true pairs {len(true)}  correct {tp}")
print(f"precision {tp / max(len(linked), 1):.3f}  recall {tp / max(len(true), 1):.3f}")
# the overview tab quotes these, so it always shows the measured numbers, never typed-in ones
import json
QUALITY = json.dumps({"precision_pct": round(100 * tp / max(len(linked), 1), 1), "recall_pct": round(100 * tp / max(len(true), 1), 1),
                      "linked_pairs": len(linked), "true_pairs": len(true), "records": len(mpi), "people": len(by_t)})
for console in ("dash", "app"):                 # both consoles read it from their own cache folder
    cache = Path(__file__).resolve().parents[1] / console / "cache"
    cache.mkdir(exist_ok=True)
    (cache / "mpi_quality.json").write_text(QUALITY)
if "-v" in sys.argv:
    for a, b in sorted(true - linked)[:15]:
        print("MISSED", a, b)
    for a, b in sorted(linked - true)[:15]:
        print("WRONG ", a, b)
