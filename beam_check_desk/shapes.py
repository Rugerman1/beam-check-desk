"""AISC W-shape properties loaded from the bundled CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files


@dataclass(frozen=True)
class Shape:
    label: str
    weight: float  # lb/ft
    a: float  # in^2
    d: float  # in
    bf: float
    tw: float
    tf: float
    ix: float  # in^4
    sx: float  # in^3
    zx: float  # in^3
    rx: float
    iy: float
    sy: float
    zy: float
    ry: float
    j: float  # in^4
    cw: float  # in^6
    rts: float
    ho: float
    bf_2tf: float
    h_tw: float

    @property
    def self_weight_kipft(self) -> float:
        return self.weight / 1000.0


_FIELDS = [
    "weight", "a", "d", "bf", "tw", "tf", "ix", "sx", "zx", "rx", "iy", "sy", "zy",
    "ry", "j", "cw", "rts", "ho", "bf_2tf", "h_tw",
]


@lru_cache(maxsize=1)
def load_shapes() -> dict[str, Shape]:
    path = files("beam_check_desk.data").joinpath("aisc_w_shapes.csv")
    shapes: dict[str, Shape] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = row["label"].strip().upper()
            shapes[label] = Shape(label=label, **{k: float(row[k]) for k in _FIELDS})
    return shapes


def get_shape(label: str) -> Shape:
    shapes = load_shapes()
    key = label.strip().upper().replace(" ", "")
    if key not in shapes:
        raise KeyError(f"Unknown shape {label!r}. Try one of {list(shapes)[:5]}...")
    return shapes[key]


def shape_labels() -> list[str]:
    return list(load_shapes())
