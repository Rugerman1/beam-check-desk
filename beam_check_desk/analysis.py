"""Statically determinate beam analysis by superposition.

Shear and moment are evaluated exactly at each grid point from the applied
loads and the computed reactions.  Deflection comes from numerically
integrating M/EI twice and fitting the support boundary conditions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import BeamInput, PointLoad, UniformLoad

GRID_POINTS = 2001


@dataclass
class Reactions:
    """Support reactions.  Forces in kips (upward positive), moment in kip-ft."""

    positions: list[float]
    forces: list[float]
    fixed_moment: float = 0.0  # only for cantilevers, at the fixed end


@dataclass
class AnalysisResult:
    x: np.ndarray  # ft
    shear: np.ndarray  # kips
    moment: np.ndarray  # kip-ft
    deflection: np.ndarray  # in, downward positive
    reactions: Reactions

    @property
    def v_max(self) -> float:
        return float(np.max(np.abs(self.shear)))

    @property
    def m_max(self) -> float:
        return float(np.max(np.abs(self.moment)))

    @property
    def m_max_pos(self) -> float:
        return float(max(np.max(self.moment), 0.0))

    @property
    def m_max_neg(self) -> float:
        return float(min(np.min(self.moment), 0.0))

    @property
    def x_at_m_max(self) -> float:
        return float(self.x[int(np.argmax(np.abs(self.moment)))])

    @property
    def defl_max(self) -> float:
        return float(np.max(np.abs(self.deflection)))

    @property
    def x_at_defl_max(self) -> float:
        return float(self.x[int(np.argmax(np.abs(self.deflection)))])


def _total_and_moment(points: list[PointLoad], uniforms: list[UniformLoad], about: float):
    """Total downward load and its moment about `about` (clockwise positive
    for loads to the right)."""
    total = 0.0
    moment = 0.0
    for p in points:
        total += p.magnitude
        moment += p.magnitude * (p.position - about)
    for u in uniforms:
        w = u.intensity * (u.end - u.start)
        total += w
        moment += w * ((u.start + u.end) / 2 - about)
    return total, moment


def reactions(beam: BeamInput, points: list[PointLoad], uniforms: list[UniformLoad]) -> Reactions:
    if beam.support == "simple":
        a, b = beam.support_a, beam.support_b
        total, m_about_a = _total_and_moment(points, uniforms, a)
        rb = m_about_a / (b - a)
        ra = total - rb
        return Reactions(positions=[a, b], forces=[ra, rb])
    if beam.support == "cantilever_left":
        total, m_about_fixed = _total_and_moment(points, uniforms, 0.0)
        # Fixed-end moment that makes M(L) = 0: hogging, so negative.
        return Reactions(positions=[0.0], forces=[total], fixed_moment=-m_about_fixed)
    # cantilever_right
    total, m_about_fixed = _total_and_moment(points, uniforms, beam.length)
    # Loads are to the left of the fixed end, so m_about_fixed is negative.
    return Reactions(positions=[beam.length], forces=[total], fixed_moment=m_about_fixed)


def _shear_moment(x: np.ndarray, beam: BeamInput, points, uniforms, rx: Reactions):
    v = np.zeros_like(x)
    m = np.zeros_like(x)
    for pos, r in zip(rx.positions, rx.forces):
        on = x >= pos - 1e-9
        v[on] += r
        m[on] += r * (x[on] - pos)
    if beam.support == "cantilever_left":
        m += rx.fixed_moment
    # For a right-hand cantilever the internal moment at x = L is already the
    # hogging fixed-end moment; the reaction moment acts beyond the beam.
    for p in points:
        on = x >= p.position - 1e-9
        v[on] -= p.magnitude
        m[on] -= p.magnitude * (x[on] - p.position)
    for u in uniforms:
        loaded = np.clip(x, u.start, u.end) - u.start  # length loaded up to x
        w = u.intensity * loaded
        v -= w
        centroid = u.start + loaded / 2
        m -= w * (x - centroid)
    # Clean the free end so tiny residuals never show as nonzero.
    m[np.isclose(np.abs(m), 0, atol=1e-9)] = 0.0
    return v, m


def _deflection(x_ft: np.ndarray, m_kipft: np.ndarray, beam: BeamInput, e_ksi: float, ix_in4: float):
    """Double integration of M/EI.  Returns inches, downward positive."""
    x = x_ft * 12.0
    curvature = m_kipft * 12.0 / (e_ksi * ix_in4)  # 1/in, sagging positive
    dx = np.diff(x)
    theta = np.concatenate([[0.0], np.cumsum((curvature[1:] + curvature[:-1]) / 2 * dx)])
    v = np.concatenate([[0.0], np.cumsum((theta[1:] + theta[:-1]) / 2 * dx)])
    # v_true = v + c1*x + c2 (upward positive with sagging-positive curvature)

    def interp(arr, pos_ft):
        return float(np.interp(pos_ft * 12.0, x, arr))

    if beam.support == "simple":
        xa, xb = beam.support_a * 12.0, beam.support_b * 12.0
        va, vb = interp(v, beam.support_a), interp(v, beam.support_b)
        c1 = -(vb - va) / (xb - xa)
        c2 = -va - c1 * xa
    else:
        xf = 0.0 if beam.support == "cantilever_left" else beam.length
        c1 = -interp(theta, xf)
        c2 = -(interp(v, xf) + c1 * xf * 12.0)
    v_true = v + c1 * x + c2
    return -v_true  # downward positive


def analyze(
    beam: BeamInput,
    points: list[PointLoad],
    uniforms: list[UniformLoad],
    e_ksi: float,
    ix_in4: float,
    n: int = GRID_POINTS,
) -> AnalysisResult:
    """Analyze the beam for exactly the loads given (already factored or
    combined by the caller)."""
    x = np.linspace(0.0, beam.length, n)
    # Make sure every load and support position is on the grid so peaks are exact.
    extra = [beam.support_a, beam.support_b] if beam.support == "simple" else []
    extra += [p.position for p in points]
    extra += [u.start for u in uniforms] + [u.end for u in uniforms]
    x = np.unique(np.concatenate([x, np.array(extra, dtype=float)]))
    rx = reactions(beam, points, uniforms)
    v, m = _shear_moment(x, beam, points, uniforms, rx)
    d = _deflection(x, m, beam, e_ksi, ix_in4)
    return AnalysisResult(x=x, shear=v, moment=m, deflection=d, reactions=rx)


def scaled_loads(beam: BeamInput, dead: float, live: float, self_weight_kipft: float):
    """Return (points, uniforms) with dead loads multiplied by `dead` and live
    loads by `live`.  Self weight is added as a dead uniform load over the
    whole beam when the input asks for it."""
    points = [
        PointLoad(p.magnitude * (dead if p.case == "D" else live), p.position, p.case, p.label)
        for p in beam.point_loads
    ]
    uniforms = [
        UniformLoad(u.intensity * (dead if u.case == "D" else live), u.start, u.end, u.case, u.label)
        for u in beam.uniform_loads
    ]
    if beam.include_self_weight and self_weight_kipft > 0:
        uniforms.append(UniformLoad(self_weight_kipft * dead, 0.0, beam.length, "D", "Self weight"))
    return points, uniforms


def compute_cb(result: AnalysisResult, start: float, end: float) -> float:
    """AISC 360 Eq. F1-1 for the unbraced segment from `start` to `end` (ft)."""
    seg = (result.x >= start - 1e-9) & (result.x <= end + 1e-9)
    m = np.abs(result.moment[seg])
    if m.size == 0 or np.max(m) == 0:
        return 1.0
    m_max = float(np.max(m))
    xs = result.x[seg]
    quarter = [np.interp(start + f * (end - start), xs, m) for f in (0.25, 0.5, 0.75)]
    ma, mb, mc = quarter
    cb = 12.5 * m_max / (2.5 * m_max + 3 * ma + 4 * mb + 3 * mc)
    return float(min(cb, 3.0))
