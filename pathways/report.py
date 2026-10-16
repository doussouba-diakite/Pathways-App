"""One-page-per-section PDF a student can print or share with a counselor."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#1b1f3b")
ACCENT = colors.HexColor("#6c5ce7")
FIT_COLOR = {"Safety": "#00b894", "Match": "#0984e3", "Reach": "#e17055", "Unknown": "#636e72"}


def _money(v) -> str:
    return "—" if pd.isna(v) else f"${v:,.0f}"


def build_pdf(colleges: pd.DataFrame, careers: pd.DataFrame, aid, name: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch, title="My Pathways Plan")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=INK, fontSize=22, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=ACCENT, spaceBefore=12)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.grey)

    who = f" for {name}" if name else ""
    story = [Paragraph(f"My Pathways Plan{who}", h1),
             Paragraph(f"Made {date.today():%B %d, %Y}. Data: U.S. College Scorecard, O*NET.", small)]

    story.append(Paragraph("My college list", h2))
    if colleges.empty:
        story.append(Paragraph("No schools saved yet.", body))
    else:
        rows = [["School", "Fit", "Net price / yr", "Grad rate", "Why"]]
        for _, r in colleges.iterrows():
            fit = f'<font color="{FIT_COLOR.get(r["fit"], "#000")}"><b>{r["fit"]}</b></font>'
            grad = "—" if pd.isna(r.get("grad_rate")) else f"{r['grad_rate']:.0%}"
            rows.append([Paragraph(f"<b>{r['name']}</b><br/>{r['city']}, {r['state']}", body),
                         Paragraph(fit, body), _money(r.get("net_cost")), grad, Paragraph(r["why"], small)])
        t = Table(rows, colWidths=[2.1 * inch, 0.7 * inch, 1.0 * inch, 0.7 * inch, 2.7 * inch], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f3ff")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dcdde1")),
        ]))
        story.append(t)

    story.append(Paragraph("Aid I may qualify for (estimates)", h2))
    story.append(Paragraph(f"Pell Grant: <b>{_money(aid.pell)}</b> &nbsp; NY TAP: <b>{_money(aid.tap)}</b> "
                           f"&nbsp; Total: <b>{_money(aid.total)}</b> per year", body))
    for note in aid.notes:
        story.append(Paragraph("• " + note, body))

    story.append(Paragraph("Careers that match my interests", h2))
    for _, c in careers.head(8).iterrows():
        story.append(Paragraph(f"<b>{c['title']}</b> ({c['match']}% match) — {c['preparation']}. {c['why']}", body))

    story += [Spacer(1, 10), Paragraph("Estimates for planning only. File the FAFSA (or the NYS Dream Act "
                                       "application) to get your real aid offer.", small)]
    doc.build(story)
    return buf.getvalue()
