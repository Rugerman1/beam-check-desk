"""Run a complete beam check: load combinations, analysis, AISC checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import __version__
from .analysis import AnalysisResult, analyze, compute_cb, scaled_loads
from .checks import CheckLine, FlexureResult, ShearResult, available, flexure, shear
from .model import BeamInput
from .shapes import Shape, get_shape

COMBOS = {
    "LRFD": {"strength": (1.2, 1.6, "1.2D + 1.6L"), "service": (1.0, 1.0, "D + L")},
    "ASD": {"strength": (1.0, 1.0, "D + L"), "service": (1.0, 1.0, "D + L")},
}


@dataclass
class BeamCheck:
    beam: BeamInput
    shape: Shape
    strength_combo: str
    strength: AnalysisResult  # factored (LRFD) or service (ASD) loads
    service_total: AnalysisResult  # D + L, unfactored
    service_live: AnalysisResult  # L only, unfactored
    flexure: FlexureResult
    shear: ShearResult
    lines: list[CheckLine] = field(default_factory=list)
    cb_computed: float | None = None
    version: str = __version__

    @property
    def governing(self) -> CheckLine:
        return max(self.lines, key=lambda c: c.ratio)

    @property
    def passes(self) -> bool:
        return all(c.status == "OK" for c in self.lines)

    @property
    def warnings(self) -> list[str]:
        out = [n for n in self.flexure.notes if "not valid" in n]
        return out


def run_check(beam: BeamInput, compute_cb_from_diagram: bool = False) -> BeamCheck:
    errors = beam.validate()
    if errors:
        raise ValueError("; ".join(errors))
    shape = get_shape(beam.shape)
    sw = shape.self_weight_kipft
    d_f, l_f, combo_name = COMBOS[beam.method]["strength"]

    pts, unis = scaled_loads(beam, d_f, l_f, sw)
    strength = analyze(beam, pts, unis, beam.e, shape.ix)
    pts, unis = scaled_loads(beam, 1.0, 1.0, sw)
    service_total = analyze(beam, pts, unis, beam.e, shape.ix)
    pts, unis = scaled_loads(beam, 0.0, 1.0, 0.0)
    service_live = analyze(beam, pts, unis, beam.e, shape.ix)

    # Unbraced length: 0 means continuously braced.
    lb_in = beam.lb * 12.0
    cb = beam.cb
    cb_computed = None
    if compute_cb_from_diagram and beam.lb > 0:
        if beam.support == "simple":
            seg = (beam.support_a, beam.support_b)
        elif beam.support == "cantilever_left":
            seg = (0.0, beam.length)
        else:
            seg = (0.0, beam.length)
        cb_computed = compute_cb(strength, *seg)
        cb = cb_computed

    flex = flexure(shape, beam.fy, beam.e, lb_in, cb)
    shr = shear(shape, beam.fy, beam.e)

    m_avail = available(flex.mn, flex.phi, flex.omega, beam.method) / 12.0  # kip-ft
    v_avail = available(shr.vn, shr.phi, shr.omega, beam.method)
    mu, vu = strength.m_max, strength.v_max
    span_in = beam.span * 12.0
    live_lim = span_in / beam.live_defl_denominator
    total_lim = span_in / beam.total_defl_denominator
    live_d = service_live.defl_max
    total_d = service_total.defl_max

    def line(name, demand, cap, unit, notes=()):
        ratio = demand / cap if cap > 0 else float("inf")
        return CheckLine(name, demand, cap, unit, ratio, "OK" if ratio <= 1.0 else "NG", list(notes))

    m_label = "phi*Mn" if beam.method == "LRFD" else "Mn/Omega"
    v_label = "phi*Vn" if beam.method == "LRFD" else "Vn/Omega"
    lines = [
        line(f"Flexure ({combo_name})", mu, m_avail, "kip-ft",
             [f"{m_label} = {m_avail:.1f} kip-ft, governed by {flex.governing}"]),
        line(f"Shear ({combo_name})", vu, v_avail, "kips",
             [f"{v_label} = {v_avail:.1f} kips"]),
        line(f"Live load deflection (L/{beam.live_defl_denominator:g})", live_d, live_lim, "in"),
        line(f"Total load deflection (L/{beam.total_defl_denominator:g})", total_d, total_lim, "in"),
    ]
    return BeamCheck(
        beam=beam, shape=shape, strength_combo=combo_name, strength=strength,
        service_total=service_total, service_live=service_live, flexure=flex,
        shear=shr, lines=lines, cb_computed=cb_computed,
    )


def summary_dict(check: BeamCheck) -> dict:
    """Plain numbers for the narrative writer and the report."""
    b = check.beam
    s = check.shape
    return {
        "shape": s.label,
        "method": b.method,
        "strength_combo": check.strength_combo,
        "length_ft": b.length,
        "support": b.support,
        "support_positions_ft": (
            [b.support_a, b.support_b] if b.support == "simple" else
            ([0.0] if b.support == "cantilever_left" else [b.length])
        ),
        "fy_ksi": b.fy,
        "e_ksi": b.e,
        "lb_ft": b.lb,
        "cb": check.flexure.cb,
        "cb_computed_from_diagram": check.cb_computed is not None,
        "point_loads": [
            {"kips": p.magnitude, "at_ft": p.position, "case": p.case} for p in b.point_loads
        ],
        "uniform_loads": [
            {"kip_per_ft": u.intensity, "from_ft": u.start, "to_ft": u.end, "case": u.case}
            for u in b.uniform_loads
        ],
        "self_weight_included": b.include_self_weight,
        "self_weight_kip_per_ft": s.self_weight_kipft,
        "reactions_kips": [round(r, 2) for r in check.strength.reactions.forces],
        "fixed_end_moment_kipft": round(check.strength.reactions.fixed_moment, 2),
        "mu_kipft": round(check.strength.m_max, 2),
        "x_at_mu_ft": round(check.strength.x_at_m_max, 2),
        "vu_kips": round(check.strength.v_max, 2),
        "mp_kipft": round(check.flexure.mp / 12, 1),
        "lp_ft": round(check.flexure.lp / 12, 2),
        "lr_ft": round(check.flexure.lr / 12, 2),
        "mn_kipft": round(check.flexure.mn / 12, 1),
        "flexure_governed_by": check.flexure.governing,
        "flange_class": check.flexure.flange_class,
        "web_class": check.flexure.web_class,
        "vn_kips": round(check.shear.vn, 1),
        "live_deflection_in": round(check.service_live.defl_max, 3),
        "total_deflection_in": round(check.service_total.defl_max, 3),
        "checks": [
            {"name": c.name, "demand": round(c.demand, 3), "capacity": round(c.capacity, 3),
             "unit": c.unit, "ratio": round(c.ratio, 3), "status": c.status}
            for c in check.lines
        ],
        "governing_check": check.governing.name,
        "governing_ratio": round(check.governing.ratio, 3),
        "passes": check.passes,
        "warnings": check.warnings,
    }
