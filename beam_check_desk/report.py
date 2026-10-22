"""PDF calc package built with ReportLab."""

from __future__ import annotations

import datetime as dt
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import __version__
from .engine import BeamCheck
from .plots import diagrams_png

DISCLAIMER = (
    "Beam Check Desk is a student-built tool for checking hand calculations. "
    "It is not a substitute for engineering judgment or a licensed engineer's review, "
    "and it is not for use on real design work."
)


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, leading=10, textColor=colors.grey))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9.5, leading=13))
    ss.add(ParagraphStyle("H", parent=ss["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=4))
    return ss


def _table(rows, col_widths=None, header=True):
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style))
    return t


def build_pdf(check: BeamCheck, narrative: str, narrative_source: str, path: str) -> None:
    ss = _styles()
    b = check.beam
    s = check.shape
    story = []
    title = f"Steel Beam Check: {s.label}"
    story.append(Paragraph(title, ss["Title"]))
    meta = [
        ["Project", b.project or "-", "Member", b.member or "-"],
        ["Engineer", b.engineer or "-", "Date", dt.date.today().isoformat()],
        ["Method", f"{b.method} ({check.strength_combo})", "Software", f"Beam Check Desk v{__version__}"],
    ]
    story.append(_table(meta, col_widths=[1.0 * inch, 2.4 * inch, 1.0 * inch, 2.4 * inch], header=False))
    story.append(Spacer(1, 8))

    verdict = "PASSES" if check.passes else "DOES NOT PASS"
    g = check.governing
    color = "#1a7f37" if check.passes else "#b42318"
    story.append(Paragraph(
        f"<font color='{color}'><b>{verdict}</b></font>. Governing check: {g.name}, "
        f"demand/capacity = {g.ratio:.3f}.", ss["Body"]))
    for w in check.warnings:
        story.append(Paragraph(f"<font color='#b42318'><b>Warning:</b> {w}</font>", ss["Body"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Inputs", ss["H"]))
    support = {
        "simple": f"Simple supports at {b.support_a:g} ft and {b.support_b:g} ft",
        "cantilever_left": "Cantilever, fixed at left end",
        "cantilever_right": "Cantilever, fixed at right end",
    }[b.support]
    inputs = [
        ["Beam length", f"{b.length:g} ft", "Supports", support],
        ["Fy", f"{b.fy:g} ksi", "E", f"{b.e:g} ksi"],
        ["Unbraced length Lb", f"{b.lb:g} ft" if b.lb > 0 else "0 ft (continuously braced)",
         "Cb", f"{check.flexure.cb:.2f}" + (" (from moment diagram)" if check.cb_computed else "")],
        ["Self weight", f"{'included' if b.include_self_weight else 'excluded'} ({s.weight:g} lb/ft)",
         "Deflection limits", f"L/{b.live_defl_denominator:g} live, L/{b.total_defl_denominator:g} total"],
    ]
    story.append(_table(inputs, col_widths=[1.3 * inch, 2.0 * inch, 1.3 * inch, 2.2 * inch], header=False))
    story.append(Spacer(1, 6))

    loads = [["Load", "Case", "Magnitude", "Location"]]
    for p in b.point_loads:
        loads.append([p.label or "Point load", p.case, f"{p.magnitude:g} kips", f"{p.position:g} ft"])
    for u in b.uniform_loads:
        loads.append([u.label or "Uniform load", u.case, f"{u.intensity:g} kip/ft", f"{u.start:g} to {u.end:g} ft"])
    if b.include_self_weight:
        loads.append(["Self weight", "D", f"{s.self_weight_kipft:.3f} kip/ft", f"0 to {b.length:g} ft"])
    if len(loads) == 1:
        loads.append(["(none)", "", "", ""])
    story.append(_table(loads, col_widths=[2.2 * inch, 0.6 * inch, 1.5 * inch, 2.0 * inch]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Section properties (AISC Shapes Database v16.0)", ss["H"]))
    props = [
        ["A", f"{s.a:g} in²", "d", f"{s.d:g} in", "bf", f"{s.bf:g} in", "tf", f"{s.tf:g} in"],
        ["tw", f"{s.tw:g} in", "Ix", f"{s.ix:g} in^4", "Sx", f"{s.sx:g} in³", "Zx", f"{s.zx:g} in³"],
        ["ry", f"{s.ry:g} in", "rts", f"{s.rts:g} in", "ho", f"{s.ho:g} in", "J", f"{s.j:g} in^4"],
        ["bf/2tf", f"{s.bf_2tf:g}", "h/tw", f"{s.h_tw:g}", "Cw", f"{s.cw:g} in^6", "wt", f"{s.weight:g} lb/ft"],
    ]
    story.append(_table(props, col_widths=[0.6 * inch, 1.1 * inch] * 4, header=False))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Analysis", ss["H"]))
    rx = check.strength.reactions
    rx_text = ", ".join(f"R at {p:g} ft = {r:.2f} kips" for p, r in zip(rx.positions, rx.forces))
    if b.support != "simple":
        rx_text += f"; fixed-end moment = {rx.fixed_moment:.2f} kip-ft"
    story.append(Paragraph(f"Reactions under {check.strength_combo}: {rx_text}.", ss["Body"]))
    story.append(Paragraph(
        f"Mu,max = {check.strength.m_max:.2f} kip-ft at {check.strength.x_at_m_max:.2f} ft; "
        f"Vu,max = {check.strength.v_max:.2f} kips. "
        f"Service deflection: live = {check.service_live.defl_max:.3f} in, "
        f"total = {check.service_total.defl_max:.3f} in at {check.service_total.x_at_defl_max:.2f} ft.",
        ss["Body"]))
    story.append(Spacer(1, 4))
    story.append(Image(io.BytesIO(diagrams_png(check)), width=6.6 * inch, height=6.6 * inch * 7.2 / 7.0))
    story.append(PageBreak())

    story.append(Paragraph("AISC 360-22 checks", ss["H"]))
    f = check.flexure
    fl = [
        ["Item", "Value"],
        ["Flange / web classification", f"{f.flange_class} / {f.web_class}"],
        ["Mp = Fy Zx", f"{f.mp / 12:.1f} kip-ft"],
        ["Lp (Eq. F2-5)", f"{f.lp / 12:.2f} ft"],
        ["Lr (Eq. F2-6)", f"{f.lr / 12:.2f} ft"],
        ["Mn, lateral-torsional buckling", f"{f.mn_ltb / 12:.1f} kip-ft"],
        ["Mn, flange local buckling", f"{f.mn_flb / 12:.1f} kip-ft"],
        ["Mn (governing: " + f.governing + ")", f"{f.mn / 12:.1f} kip-ft"],
        ["Aw = d tw", f"{check.shear.aw:.2f} in²"],
        ["Cv1", f"{check.shear.cv1:.3f}"],
        ["Vn = 0.6 Fy Aw Cv1", f"{check.shear.vn:.1f} kips"],
        ["Resistance / safety factors",
         f"phi_b = {f.phi:.2f}, Omega_b = {f.omega:.2f}; phi_v = {check.shear.phi:.2f}, Omega_v = {check.shear.omega:.2f}"],
    ]
    story.append(_table(fl, col_widths=[3.0 * inch, 3.6 * inch]))
    for n in f.notes + check.shear.notes:
        story.append(Paragraph(n, ss["Small"]))
    story.append(Spacer(1, 8))

    rows = [["Check", "Demand", "Capacity", "Ratio", "Status"]]
    for c in check.lines:
        rows.append([c.name, f"{c.demand:.3f} {c.unit}", f"{c.capacity:.3f} {c.unit}", f"{c.ratio:.3f}", c.status])
    t = _table(rows, col_widths=[2.6 * inch, 1.2 * inch, 1.2 * inch, 0.7 * inch, 0.7 * inch])
    for i, c in enumerate(check.lines, start=1):
        t.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), colors.HexColor("#1a7f37" if c.status == "OK" else "#b42318")),
                               ("FONTNAME", (4, i), (4, i), "Helvetica-Bold")]))
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Narrative" + (" (written by Claude from the computed values)" if narrative_source == "claude" else ""), ss["H"]))
    for para in narrative.split("\n\n"):
        story.append(Paragraph(para.strip(), ss["Body"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 10))
    story.append(Paragraph(DISCLAIMER, ss["Small"]))

    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch, title=title)
    doc.build(story)
