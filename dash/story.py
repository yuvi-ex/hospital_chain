"""Tab 1 · the problem statement as one picture: her information sits in three systems that do not know each other;
Exasol brings it together into one patient view. Names, IDs and the alert are read live (fallback: last good run).
"""
import how

CSS = """
.ps-h { font-size:2rem; font-weight:900; letter-spacing:-.03em; color:var(--ink2); margin:.3rem 0 .2rem; line-height:1.15; }
.ps-h em { font-style:normal; color:#12796A; }
.k4s { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.7rem; margin-top:.8rem; }
.k4 { display:flex; gap:.7rem; align-items:center; border-radius:16px; border:1px solid var(--edge); background:#fff; padding:.6rem .85rem; }
.k4 svg { flex:0 0 32px; width:32px; height:32px; } .k4 .v { font-size:1.35rem; font-weight:900; color:var(--ink2); line-height:1.1; }
.k4.good .v { color:#12796A; } .k4.bad .v { color:#C8102E; } .k4 .l { font-size:.8rem; color:var(--muted); }
.k4 .go { font-size:.62rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:#12796A; margin-top:.15rem; }
@media (max-width:1000px) { .k4s { grid-template-columns:1fr 1fr; } }
"""


def _t(x, y, txt, size=12, weight=600, color="#0B1B34", anchor="middle", opacity=None):
    o = f' opacity="{opacity}"' if opacity else ""
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" fill="{color}"{o}>{txt}</text>'


def _rec(who, label):
    return next((r for r in who if r.get("SOURCE_LABEL") == label), {})


def _picture(records, people, blind, rh, rt, scans):
    """Today (the doctor sees only her own branch's system) vs with Exasol (one question -> one engine over the three
    systems -> one patient view: who she is, the allergy clash, the readmissions nobody could count)."""
    I = how._i
    out = ['<svg viewBox="0 0 1240 400" role="img" aria-label="Today versus with Exasol">',
           '<defs><marker id="ov-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="14" markerHeight="14" markerUnits="userSpaceOnUse" orient="auto">'
           '<path d="M0 0 L10 5 L0 10 z" fill="#9FB0C4"/></marker></defs>']
    # ---- today: the doctor reaches only the system of her own branch
    out.append('<rect x="10" y="10" width="430" height="380" rx="24" fill="#FFF7F8" stroke="#F3C2C8"/>')
    out.append(_t(30, 42, "TODAY", 13, 900, "#B00D27", "start"))
    tiles = [(30, 70, "#C56A00", how.I_DB, "Legacy system", "Postgres &middot; Branch A", False, "M196 190 C170 180 175 130 155 122"),
             (272, 70, "#0076AD", how.I_DOCS, "Modern platform", "MongoDB &middot; Branch B", True, "M264 190 C290 180 280 130 290 122"),
             (157, 300, "#7A4FD6", how.I_IMG, "Scans", "Amazon S3 &middot; DICOM", False, "M230 242 L230 298")]
    for x, y, c, ic, t, s, sees, d in tiles:
        if sees:
            out.append(f'<path d="{d}" fill="none" stroke="#12796A" stroke-width="2.5"/>')
        else:
            out.append(f'<path d="{d}" fill="none" stroke="#C8102E" stroke-width="2" stroke-dasharray="5 5" opacity=".7"/>')
        out.append(f'<rect x="{x}" y="{y}" width="150" height="52" rx="12" fill="{c}"{"" if sees else " opacity=\".55\""}/>'
                   + I(ic, x + 10, y + 14, 1.0, "#fff", 2.2) + _t(x + 40, y + 24, t, 12.5, 800, "#fff", "start")
                   + _t(x + 40, y + 40, s, 9.5, 600, "#fff", "start", ".85"))
    for cx, cy in [(172, 150), (232, 272)]:  # the two systems the doctor cannot see
        out.append(f'<circle cx="{cx}" cy="{cy}" r="10" fill="#fff" stroke="#C8102E" stroke-width="2"/>'
                   f'<path d="M{cx - 4} {cy - 4}l8 8M{cx + 4} {cy - 4}l-8 8" stroke="#C8102E" stroke-width="2" stroke-linecap="round"/>')
    out.append('<circle cx="230" cy="206" r="36" fill="#fff" stroke="#C8102E" stroke-width="2.5"/>' + I(how.I_USER, 212, 188, 1.5, "#B00D27", 1.8))
    out.append(_t(330, 206, "1 of 3", 20, 900, "#B00D27", "start") + _t(330, 224, "systems in", 12, 600, "#8E0A20", "start")
               + _t(330, 239, "front of the doctor", 12, 600, "#8E0A20", "start"))
    out.append(_t(225, 380, "patient details and health records split across systems", 12, 600, "#8E0A20"))
    # ---- the turn
    out.append('<line x1="452" y1="206" x2="528" y2="206" stroke="#9FB0C4" stroke-width="4" marker-end="url(#ov-ah)"/>')
    # ---- with Exasol
    out.append('<rect x="540" y="10" width="690" height="380" rx="24" fill="#F2FBF8" stroke="#CDEBE4"/>')
    out.append(_t(560, 42, "WITH EXASOL", 13, 900, "#12796A", "start"))
    for y, c, ic, t in [(160, "#0E2A47", how.I_USER, "Doctor"), (208, "#5B5FE0", how.I_BOT, "AI agent")]:
        out.append(f'<rect x="562" y="{y}" width="100" height="40" rx="11" fill="#fff" stroke="{c}" stroke-width="2.2"/>'
                   + I(ic, 570, y + 9, 0.95, c, 2.2) + _t(598, y + 25, t, 12.5, 800, c, "start"))
    out.append(_t(612, 278, "one question", 15, 900) + _t(612, 295, "the same path for both", 11.5, 500, "#5B6B80"))
    out.append('<line x1="670" y1="210" x2="733" y2="210" stroke="#9FB0C4" stroke-width="3" marker-end="url(#ov-ah)"/>')
    for k, (c, ic, t) in enumerate([("#C56A00", how.I_DB, "Legacy"), ("#0076AD", how.I_DOCS, "Modern"), ("#7A4FD6", how.I_IMG, "Scans")]):
        x = 752 + k * 82
        out.append(f'<rect x="{x}" y="58" width="74" height="44" rx="11" fill="{c}"/>' + I(ic, x + 25, 63, 1.0, "#fff", 2.2)
                   + _t(x + 37, 97, t, 9.5, 800, "#fff"))
        out.append(f'<line x1="{x + 37}" y1="104" x2="{x + 37}" y2="136" stroke="{c}" stroke-width="2.5" stroke-dasharray="4 4"/>')
    out.append(_t(1010, 76, "federated,", 11.5, 700, "#12796A", "start") + _t(1010, 91, "read in place", 11.5, 700, "#12796A", "start"))
    out.append('<rect x="740" y="138" width="260" height="150" rx="24" fill="#0B3B4A"/><rect x="740" y="138" width="260" height="150" rx="24" fill="#12796A" opacity=".55"/>')
    out.append(_t(870, 172, "Exasol", 26, 900, "#fff") + _t(870, 196, "federates each system where it is,", 12, 500, "#fff")
               + _t(870, 213, "matches the records to one person,", 12, 500, "#fff") + _t(870, 230, "answers through semantic views", 12, 500, "#fff"))
    out.append('<rect x="772" y="248" width="196" height="24" rx="12" fill="rgba(255,255,255,.16)"/>'
               + _t(870, 264, "FEDERATED &middot; SEMANTIC VIEWS", 10.5, 800, "#fff"))
    rows = [(140, "#1FA08B", how.I_OK, f"{people:,} people", f"from {records:,} records"),
            (213, "#C8102E", how.I_ALERT, f"{blind} patients", "allergy clash, in a bed now"),
            (286, "#D98A00", how.I_TREND, f"{100 * rh / max(rt, 1):.0f}%", "of readmissions cross a branch")]
    for y, c, ic, v, l in rows:
        out.append(f'<path d="M1002 213 C1025 213 1025 {y} 1046 {y}" fill="none" stroke="{c}" stroke-width="2.5"/>')
        out.append(I(ic, 1050, y - 15, 1.25, c, 2.2) + _t(1086, y + 4, v, 22, 900, c, "start") + _t(1086, y + 20, l, 10.5, 600, "#5B6B80", "start"))
    out.append(_t(885, 340, f"one patient view in about a second, with {scans} earlier scans from S3", 14, 800, "#12796A")
               + _t(885, 360, "the doctor sees the allergy before the first dose", 12, 500, "#5B6B80"))
    out.append('</svg>')
    return "".join(out)


def problem(who, allergy, chain, readm, mpi, inbed):
    """Each argument is a run() result dict."""
    w = who["rows"]
    pacs = [r for r in w if r.get("SOURCE_LABEL") == "PACS on S3"]
    m = (mpi["rows"] or [{}])[0]
    rec, ppl = int(m.get("RECORDS") or 0), int(m.get("PEOPLE") or 0)
    rr = readm["rows"]
    rt, rh = sum(int(r["READMISSIONS"]) for r in rr), sum(int(r["HIDDEN"]) for r in rr)
    blind = sum(1 for r in chain["rows"] if str(r.get("KNOWN_WHERE_PRESCRIBED")).lower() == "false")
    live = all(x["live"] for x in (who, allergy, chain, readm, mpi, inbed))
    note = "" if live else '<div class="cached">A source was unavailable: some values are from the last good run.</div>'
    return f'''<div class="ov-band" style="margin-top:.4rem"><div class="ov-k">The problem</div>
<div class="ps-h">Her history sits in three systems. <em>Exasol brings them together, live.</em></div></div>
<div class="hw-pic">{_picture(rec, ppl, blind, rh, rt, len(pacs) or 3)}</div>{note}'''
