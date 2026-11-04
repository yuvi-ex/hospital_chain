"""Tab 'How it works': the whole system as ONE picture, few words (same visual language as the loan demo's How it works).
Left to right: a doctor or an agent asks one question (1), Exasol checks who is asking (2), reads the three systems where
the data already lives and matches the records to one person (3), builds one patient view (4), the answer goes out as an
alert, the earlier scans and the cross-branch counts, and every query lands in the audit log (5).
The one number inside the picture (records -> people) is read live; the rest is static on purpose: the next tabs do it live.
"""

CSS = """
.hw-h { font-size:1.9rem; font-weight:900; letter-spacing:-.03em; color:var(--ink2); margin:.3rem 0 .1rem; line-height:1.15; }
.hw-h em { font-style:normal; color:#12796A; }
.hw-pic { margin-top:.6rem; border-radius:24px; border:1px solid var(--edge); background:#fff; box-shadow:var(--shadow); padding:.6rem .8rem; overflow-x:auto; }
.hw-pic svg { display:block; width:100%; min-width:900px; height:auto; }
.hw-pic text { font-family:inherit; }
.hw3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; margin-top:.8rem; }
.hw3 > div { display:flex; align-items:center; gap:.7rem; border-radius:16px; background:#F2FBF8; border:1px solid #CDEBE4; padding:.6rem .9rem; }
.hw3 svg { flex:0 0 34px; width:34px; height:34px; } .hw3 b { font-size:1.05rem; color:var(--ink2); display:block; } .hw3 span { font-size:.82rem; color:var(--muted); }
details.hw-more { margin-top:1rem; } details.hw-more > summary { cursor:pointer; font-weight:800; color:#12796A; font-size:.95rem; }
@media (max-width:900px) { .hw3 { grid-template-columns:1fr; } }
"""

# 24x24 line icons, drawn into the picture with a translate + scale
I_USER = '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>'
I_BOT = '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4M9 13v1M15 13v1M9 17h6"/><circle cx="12" cy="3" r="1"/>'
I_SHIELD = '<path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z"/><path d="M9 12l2 2 4-4"/>'
I_DB = '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'
I_DOCS = '<path d="M8 3h8l4 4v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>'
I_IMG = '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>'
I_HEART = '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21.2l8.8-8.8a5.5 5.5 0 0 0 0-7.8z"/><path d="M6 12h3l1.5-2.5 2.5 5 1.5-2.5H18"/>'
I_ALERT = '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>'
I_TREND = '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'
I_LOCK = '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>'
I_COPY = '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V5a1 1 0 0 1 1-1h11"/><path d="M3 3l18 18"/>'
I_CLOCK = '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
I_BOOK = '<path d="M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4z"/><path d="M20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6z"/>'


def _i(path, x, y, s=2.0, color="#0B1B34", sw=1.7):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</g>')


def _num(n, x, y):
    return f'<circle cx="{x}" cy="{y}" r="15" fill="#0B1B34"/><text x="{x}" y="{y + 5}" text-anchor="middle" font-size="15" font-weight="900" fill="#fff">{n}</text>'


def _label(x, y, big, small, color="#0B1B34", anchor="middle"):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="17" font-weight="800" fill="{color}">{big}</text>'
            f'<text x="{x}" y="{y + 20}" text-anchor="{anchor}" font-size="13" fill="#5B6B80">{small}</text>')


def _svg_icon(path, color="#12796A"):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round">{path}</svg>')


def picture(records=1609, people=1224):
    W, H = 1240, 470
    arrow = '<path d="M0 0 L10 5 L0 10 z" fill="#9FB0C4"/>'
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="How one question becomes one patient view">',
           f'<defs><marker id="hw-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="14" markerHeight="14" markerUnits="userSpaceOnUse" orient="auto">{arrow}</marker></defs>']
    # 1 who asks: a doctor or an AI agent, the same path for both
    for y, c, ic, t in [(196, "#0E2A47", I_USER, "Doctor"), (262, "#5B5FE0", I_BOT, "AI agent")]:
        out.append(f'<rect x="40" y="{y}" width="112" height="54" rx="14" fill="#fff" stroke="{c}" stroke-width="2.5"/>'
                   + _i(ic, 50, y + 13, 1.2, c, 2) +
                   f'<text x="84" y="{y + 33}" font-size="14" font-weight="800" fill="{c}">{t}</text>')
    out.append(_num(1, 45, 190) + _label(96, 362, "One question", "from a doctor or an agent"))
    # 2 who is asking
    out.append('<line x1="160" y1="250" x2="228" y2="250" stroke="#9FB0C4" stroke-width="3" marker-end="url(#hw-ah)"/>')
    out.append('<circle cx="285" cy="250" r="52" fill="#EEF0FF" stroke="#5B5FE0" stroke-width="2.5"/>' + _i(I_SHIELD, 261, 226, 2.0, "#5B5FE0"))
    out.append(_num(2, 245, 192) + _label(285, 335, "Access check", "only what they may see"))
    # where the data lives: three systems on top, read in place by the hub
    srcs = [(468, "#C56A00", I_DB, "Legacy system", "Postgres &middot; Branch A"), (620, "#0076AD", I_DOCS, "Modern platform", "MongoDB &middot; Branch B"),
            (772, "#7A4FD6", I_IMG, "Scans", "Amazon S3 &middot; DICOM")]
    for x, c, ic, t, s in srcs:
        out.append(f'<rect x="{x - 70}" y="18" width="140" height="96" rx="18" fill="{c}"/>' + _i(ic, x - 18, 30, 1.5, "#fff", 2))
        out.append(f'<text x="{x}" y="88" text-anchor="middle" font-size="15" font-weight="800" fill="#fff">{t}</text>'
                   f'<text x="{x}" y="104" text-anchor="middle" font-size="11.5" fill="#fff" opacity=".85">{s}</text>')
        out.append(f'<line x1="{x}" y1="116" x2="{620 + (x - 620) * .35}" y2="150" stroke="{c}" stroke-width="3" stroke-dasharray="6 6"/>')
    out.append('<text x="870" y="62" font-size="13" font-weight="700" fill="#12796A">each system stays where it is,</text>'
               '<text x="870" y="80" font-size="13" font-weight="700" fill="#12796A">read in place, read-only</text>')
    # 3 the hub: what happens inside Exasol, top to bottom
    out.append('<line x1="340" y1="250" x2="448" y2="250" stroke="#9FB0C4" stroke-width="3" marker-end="url(#hw-ah)"/>')
    out.append('<rect x="455" y="150" width="330" height="232" rx="28" fill="#0B3B4A"/>'
               '<rect x="455" y="150" width="330" height="232" rx="28" fill="#12796A" opacity=".55"/>')
    out.append('<text x="620" y="186" text-anchor="middle" font-size="26" font-weight="900" fill="#fff">Exasol</text>')
    inner = [("Federated query", "in place"), ("Patient index", f"{records:,} &rarr; {people:,} people"),
             ("Semantic views", "one certified definition"), ("Clinical rules", "allergy &middot; readmission")]
    for k, (t, d) in enumerate(inner):
        y = 200 + k * 44
        out.append(f'<rect x="475" y="{y}" width="290" height="36" rx="12" fill="rgba(255,255,255,.14)"/>'
                   f'<circle cx="494" cy="{y + 18}" r="10" fill="#fff"/><text x="494" y="{y + 22}" text-anchor="middle" font-size="11" font-weight="900" fill="#0B3B4A">{chr(97 + k)}</text>'
                   f'<text x="514" y="{y + 23}" font-size="14" font-weight="800" fill="#fff">{t}</text>'
                   f'<text x="755" y="{y + 23}" text-anchor="end" font-size="11.5" fill="#fff" opacity=".85">{d}</text>')
    out.append(_num(3, 470, 152))
    # 4 one patient view
    out.append('<line x1="790" y1="250" x2="838" y2="250" stroke="#9FB0C4" stroke-width="3" marker-end="url(#hw-ah)"/>')
    out.append('<circle cx="890" cy="250" r="48" fill="#E3F5F1" stroke="#12796A" stroke-width="2.5"/>' + _i(I_HEART, 866, 226, 2.0, "#12796A"))
    out.append(_num(4, 852, 196) + _label(890, 330, "One patient", "every record, every branch"))
    # three things the doctor gets
    outs = [(165, "#C8102E", I_ALERT, "Allergy alert", "before the first dose"), (250, "#7A4FD6", I_IMG, "Earlier scans", "straight from S3"),
            (335, "#12796A", I_TREND, "Readmissions", "counted across branches")]
    for y, c, ic, t, s in outs:
        out.append(f'<path d="M940 250 C975 250 975 {y} 1010 {y}" fill="none" stroke="{c}" stroke-width="3" marker-end="url(#hw-ah)"/>')
        out.append(_i(ic, 1018, y - 18, 1.5, c, 2.2) + _label(1060, y - 2, t, s, c, "start"))
    # 5 the audit log
    out.append('<line x1="40" y1="410" x2="1200" y2="410" stroke="#E6EBF2" stroke-width="2"/>')
    out.append(_num(5, 440, 438) + _i(I_LOCK, 470, 422, 1.3, "#0B1B34"))
    out.append('<text x="510" y="443" font-size="15" font-weight="800" fill="#0B1B34">Every query is logged</text>'
               '<text x="690" y="443" font-size="13" fill="#5B6B80">who asked, doctor or agent, and what was refused</text>')
    out.append('</svg>')
    return "".join(out)


def page(records=1609, people=1224):
    take = [(I_COPY, "Federated", "each system is queried where it runs"),
            (I_CLOCK, "Before the first dose", "the alert arrives while it still matters"),
            (I_BOOK, "One rule book", "people and agents use the same views and log")]
    return (f'<div class="ov-band" style="margin-top:.4rem"><div class="ov-k">How it works</div>'
            f'<div class="hw-h">Three systems in, one patient out. <em>Federated, through semantic views.</em></div></div>'
            f'<div class="hw-pic">{picture(records, people)}</div>'
            f'<div class="hw3">{"".join(f"<div>{_svg_icon(i)}<div><b>{t}</b><span>{s}</span></div></div>" for i, t, s in take)}</div>')

I_OK = '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>'
I_NO = '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>'
