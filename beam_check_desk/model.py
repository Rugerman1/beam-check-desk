"""Input model for a single-span steel beam.

Units everywhere in this module: kips, feet, ksi, inches for section
properties (the AISC shapes table is in inches).  Loads act downward when
positive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LoadCase = Literal["D", "L"]
SupportType = Literal["simple", "cantilever_left", "cantilever_right"]
Method = Literal["LRFD", "ASD"]


@dataclass
class PointLoad:
    magnitude: float  # kips, downward positive
    position: float  # ft from the left end
    case: LoadCase = "D"
    label: str = ""


@dataclass
class UniformLoad:
    intensity: float  # kip/ft, downward positive
    start: float  # ft from the left end
    end: float  # ft from the left end
    case: LoadCase = "D"
    label: str = ""


@dataclass
class BeamInput:
    shape: str = "W18X50"
    length: float = 20.0  # total beam length, ft
    support: SupportType = "simple"
    support_a: float = 0.0  # left support position, ft (simple only)
    support_b: float = 20.0  # right support position, ft (simple only)
    fy: float = 50.0  # ksi
    e: float = 29000.0  # ksi
    lb: float = 0.0  # unbraced length of compression flange, ft (0 = fully braced)
    cb: float = 1.0
    method: Method = "LRFD"
    include_self_weight: bool = True
    live_defl_denominator: float = 360.0  # L/360
    total_defl_denominator: float = 240.0  # L/240
    point_loads: list[PointLoad] = field(default_factory=list)
    uniform_loads: list[UniformLoad] = field(default_factory=list)
    project: str = ""
    member: str = ""
    engineer: str = ""

    @property
    def span(self) -> float:
        """Length used for deflection limits: distance between supports,
        or the cantilever length."""
        if self.support == "simple":
            return self.support_b - self.support_a
        return self.length

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.length <= 0:
            errors.append("Beam length must be positive.")
        if self.support == "simple":
            if not (0 <= self.support_a < self.support_b <= self.length):
                errors.append(
                    "Supports must satisfy 0 <= left < right <= length."
                )
        if self.fy <= 0 or self.e <= 0:
            errors.append("Fy and E must be positive.")
        if self.lb < 0:
            errors.append("Unbraced length cannot be negative.")
        if self.cb <= 0:
            errors.append("Cb must be positive.")
        for p in self.point_loads:
            if not (0 <= p.position <= self.length):
                errors.append(f"Point load at {p.position} ft is off the beam.")
        for u in self.uniform_loads:
            if not (0 <= u.start < u.end <= self.length):
                errors.append(
                    f"Uniform load from {u.start} to {u.end} ft is off the beam "
                    "or has zero length."
                )
        return errors
