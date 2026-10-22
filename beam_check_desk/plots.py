"""Shear, moment and deflection diagrams rendered with matplotlib."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .engine import BeamCheck  # noqa: E402


def diagrams_png(check: BeamCheck, width_in: float = 7.0, dpi: int = 150) -> bytes:
    s = check.strength
    sv = check.service_total
    fig, axes = plt.subplots(3, 1, figsize=(width_in, 7.2), sharex=True)
    specs = [
        (axes[0], s.x, s.shear, "Shear (kips)", "#1f77b4"),
        (axes[1], s.x, s.moment, "Moment (kip-ft)", "#d62728"),
        (axes[2], sv.x, sv.deflection, "Deflection, D+L (in)", "#2ca02c"),
    ]
    for ax, x, y, label, color in specs:
        ax.fill_between(x, 0, y, color=color, alpha=0.25)
        ax.plot(x, y, color=color, linewidth=1.4)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_ylabel(label)
        ax.grid(True, linewidth=0.4, alpha=0.5)
        i = int(abs(y).argmax())
        ax.annotate(f"{y[i]:.2f}", (x[i], y[i]), textcoords="offset points", xytext=(4, 4), fontsize=8)
    axes[2].invert_yaxis()
    axes[2].set_xlabel("Position along beam (ft)")
    b = check.beam
    pos = [b.support_a, b.support_b] if b.support == "simple" else (
        [0.0] if b.support == "cantilever_left" else [b.length]
    )
    for ax in axes:
        for p in pos:
            ax.axvline(p, color="gray", linestyle="--", linewidth=0.8)
    fig.suptitle(f"{check.shape.label}  |  {check.strength_combo}", fontsize=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    return buf.getvalue()
