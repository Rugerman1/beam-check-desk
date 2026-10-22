import os

import pytest

from beam_check_desk.engine import run_check, summary_dict
from beam_check_desk.model import BeamInput, PointLoad, UniformLoad
from beam_check_desk.narrative import template_narrative


def example_beam(**kw):
    args = dict(shape="W18X50", length=24, support_a=0, support_b=24, lb=0,
                uniform_loads=[UniformLoad(0.5, 0, 24, "D"), UniformLoad(1.0, 0, 24, "L")],
                include_self_weight=True)
    args.update(kw)
    return BeamInput(**args)


def test_lrfd_combo_and_self_weight():
    check = run_check(example_beam())
    # wu = 1.2*(0.5 + 0.050) + 1.6*1.0 = 2.26 kip/ft; Mu = wu L^2 / 8
    assert check.strength.m_max == pytest.approx(2.26 * 24**2 / 8, rel=1e-6)
    assert check.lines[0].capacity == pytest.approx(379, abs=1)
    assert check.passes
    assert check.governing.name.startswith("Flexure")


def test_asd_uses_service_loads():
    check = run_check(example_beam(method="ASD"))
    assert check.strength.m_max == pytest.approx(1.55 * 24**2 / 8, rel=1e-6)
    assert check.lines[0].capacity == pytest.approx(252, abs=1)


def test_failing_beam_reports_ng():
    beam = example_beam(shape="W12X26", lb=24)
    check = run_check(beam)
    assert not check.passes
    assert any(c.status == "NG" for c in check.lines)
    s = summary_dict(check)
    assert s["passes"] is False
    text = template_narrative(s)
    assert "does not pass" in text


def test_cb_from_diagram():
    check = run_check(example_beam(lb=24), compute_cb_from_diagram=True)
    assert check.cb_computed == pytest.approx(1.14, abs=0.01)
    assert check.flexure.cb == check.cb_computed


def test_invalid_input_raises():
    with pytest.raises(ValueError):
        run_check(BeamInput(length=10, support_a=0, support_b=12))


def test_pdf_builds(tmp_path):
    pytest.importorskip("matplotlib")
    from beam_check_desk.report import build_pdf
    check = run_check(example_beam(point_loads=[PointLoad(8, 12, "L", "Girder")]))
    out = tmp_path / "calc.pdf"
    build_pdf(check, template_narrative(summary_dict(check)), "template", str(out))
    assert out.stat().st_size > 20_000
