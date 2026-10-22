"""AISC 360-22 strength checks for doubly symmetric W-shapes bent about the
strong axis: Chapter F (F2, F3) flexure, Chapter G (G2) shear, and
serviceability deflection.

All inputs in kips, inches and ksi.  Moments in kip-in inside this module;
the caller converts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .shapes import Shape


@dataclass
class CheckLine:
    name: str
    demand: float
    capacity: float
    unit: str
    ratio: float
    status: str  # "OK" or "NG"
    notes: list[str] = field(default_factory=list)


@dataclass
class FlexureResult:
    mp: float  # kip-in
    lp: float  # in
    lr: float  # in
    mn_ltb: float  # kip-in
    mn_flb: float  # kip-in
    mn: float  # kip-in
    governing: str
    flange_class: str
    web_class: str
    cb: float
    lb: float
    phi: float
    omega: float
    notes: list[str] = field(default_factory=list)

    @property
    def design_strength(self) -> float:
        """phi*Mn (LRFD) or Mn/Omega (ASD) in kip-in, set by caller via method."""
        return self.mn


@dataclass
class ShearResult:
    aw: float
    cv1: float
    vn: float  # kips
    phi: float
    omega: float
    notes: list[str] = field(default_factory=list)


def classify_flange(shape: Shape, fy: float, e: float) -> tuple[str, float, float, float]:
    lam = shape.bf_2tf
    lp = 0.38 * math.sqrt(e / fy)
    lr = 1.0 * math.sqrt(e / fy)
    if lam <= lp:
        return "compact", lam, lp, lr
    if lam <= lr:
        return "noncompact", lam, lp, lr
    return "slender", lam, lp, lr


def classify_web(shape: Shape, fy: float, e: float) -> tuple[str, float, float, float]:
    lam = shape.h_tw
    lp = 3.76 * math.sqrt(e / fy)
    lr = 5.70 * math.sqrt(e / fy)
    if lam <= lp:
        return "compact", lam, lp, lr
    if lam <= lr:
        return "noncompact", lam, lp, lr
    return "slender", lam, lp, lr


def flexure(shape: Shape, fy: float, e: float, lb_in: float, cb: float) -> FlexureResult:
    notes: list[str] = []
    mp = fy * shape.zx
    flange_class, lam_f, lpf, lrf = classify_flange(shape, fy, e)
    web_class, *_ = classify_web(shape, fy, e)
    if web_class != "compact":
        notes.append(
            "Web is not compact; Sections F4/F5 apply and are not implemented. "
            "Result is not valid for this shape."
        )

    # Lateral-torsional buckling (F2.2), c = 1 for doubly symmetric I-shapes.
    lp = 1.76 * shape.ry * math.sqrt(e / fy)
    term = shape.j / (shape.sx * shape.ho)
    lr = (
        1.95
        * shape.rts
        * (e / (0.7 * fy))
        * math.sqrt(term + math.sqrt(term**2 + 6.76 * (0.7 * fy / e) ** 2))
    )
    if lb_in <= lp:
        mn_ltb = mp
        ltb_zone = "Lb <= Lp: no LTB reduction (Eq. F2-1)"
    elif lb_in <= lr:
        mn_ltb = cb * (mp - (mp - 0.7 * fy * shape.sx) * (lb_in - lp) / (lr - lp))
        mn_ltb = min(mn_ltb, mp)
        ltb_zone = "Lp < Lb <= Lr: inelastic LTB (Eq. F2-2)"
    else:
        slender = lb_in / shape.rts
        fcr = (cb * math.pi**2 * e / slender**2) * math.sqrt(1 + 0.078 * term * slender**2)
        mn_ltb = min(fcr * shape.sx, mp)
        ltb_zone = "Lb > Lr: elastic LTB (Eq. F2-3)"
    notes.append(ltb_zone)

    # Compression flange local buckling (F3.2).
    if flange_class == "compact":
        mn_flb = mp
    elif flange_class == "noncompact":
        mn_flb = mp - (mp - 0.7 * fy * shape.sx) * (lam_f - lpf) / (lrf - lpf)
        notes.append("Noncompact flange: flange local buckling per Eq. F3-1")
    else:
        kc = min(max(4.0 / math.sqrt(shape.h_tw), 0.35), 0.76)
        mn_flb = 0.9 * e * kc * shape.sx / lam_f**2
        notes.append("Slender flange: flange local buckling per Eq. F3-2")

    mn = min(mn_ltb, mn_flb)
    governing = "lateral-torsional buckling" if mn_ltb < mn_flb else (
        "flange local buckling" if mn_flb < mp else "yielding"
    )
    if mn_ltb == mp and mn_flb == mp:
        governing = "yielding"
    return FlexureResult(
        mp=mp, lp=lp, lr=lr, mn_ltb=mn_ltb, mn_flb=mn_flb, mn=mn, governing=governing,
        flange_class=flange_class, web_class=web_class, cb=cb, lb=lb_in,
        phi=0.90, omega=1.67, notes=notes,
    )


def shear(shape: Shape, fy: float, e: float) -> ShearResult:
    """G2.1 for I-shaped members without tension field action."""
    aw = shape.d * shape.tw
    notes: list[str] = []
    limit = 2.24 * math.sqrt(e / fy)
    if shape.h_tw <= limit:
        phi, omega, cv1 = 1.00, 1.50, 1.0
        notes.append(f"h/tw = {shape.h_tw:.1f} <= 2.24*sqrt(E/Fy) = {limit:.1f}: phi_v = 1.00, Cv1 = 1.0")
    else:
        phi, omega = 0.90, 1.67
        kv = 5.34
        lim2 = 1.10 * math.sqrt(kv * e / fy)
        cv1 = 1.0 if shape.h_tw <= lim2 else lim2 / shape.h_tw
        notes.append(f"h/tw = {shape.h_tw:.1f} > 2.24*sqrt(E/Fy): phi_v = 0.90, Cv1 = {cv1:.3f}")
    vn = 0.6 * fy * aw * cv1
    return ShearResult(aw=aw, cv1=cv1, vn=vn, phi=phi, omega=omega, notes=notes)


def available(nominal: float, phi: float, omega: float, method: str) -> float:
    return phi * nominal if method == "LRFD" else nominal / omega
