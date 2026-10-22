import math

import pytest

from beam_check_desk.analysis import analyze, compute_cb
from beam_check_desk.model import BeamInput, PointLoad, UniformLoad

E = 29000.0
IX = 800.0  # W18x50


def test_simple_span_uniform_load_matches_textbook():
    beam = BeamInput(length=20, support="simple", support_a=0, support_b=20)
    res = analyze(beam, [], [UniformLoad(1.0, 0, 20)], E, IX)
    assert res.reactions.forces == pytest.approx([10, 10])
    assert res.m_max == pytest.approx(1.0 * 20**2 / 8, rel=1e-6)  # wL^2/8 = 50
    assert res.v_max == pytest.approx(10.0)
    expected = 5 * (1.0 / 12) * (240**4) / (384 * E * IX)  # 5wL^4/384EI, w in kip/in
    assert res.defl_max == pytest.approx(expected, rel=1e-4)
    assert res.x_at_defl_max == pytest.approx(10.0, abs=0.02)


def test_simple_span_point_load_at_midspan():
    beam = BeamInput(length=20, support="simple", support_a=0, support_b=20)
    res = analyze(beam, [PointLoad(10.0, 10.0)], [], E, IX)
    assert res.m_max == pytest.approx(10 * 20 / 4)  # PL/4 = 50
    expected = 10 * 240**3 / (48 * E * IX)  # PL^3/48EI
    assert res.defl_max == pytest.approx(expected, rel=1e-4)


def test_cantilever_point_load_at_tip():
    beam = BeamInput(length=10, support="cantilever_left")
    res = analyze(beam, [PointLoad(5.0, 10.0)], [], E, IX)
    assert res.reactions.forces == pytest.approx([5.0])
    assert res.reactions.fixed_moment == pytest.approx(-50.0)  # PL hogging
    assert res.m_max == pytest.approx(50.0)
    assert res.moment[-1] == pytest.approx(0.0, abs=1e-9)
    expected = 5 * 120**3 / (3 * E * IX)  # PL^3/3EI
    assert res.defl_max == pytest.approx(expected, rel=1e-4)
    assert res.x_at_defl_max == pytest.approx(10.0)


def test_cantilever_fixed_at_right_mirrors_left():
    left = analyze(BeamInput(length=10, support="cantilever_left"), [], [UniformLoad(2.0, 0, 10)], E, IX)
    right = analyze(BeamInput(length=10, support="cantilever_right"), [], [UniformLoad(2.0, 0, 10)], E, IX)
    assert left.m_max == pytest.approx(2.0 * 10**2 / 2)  # wL^2/2 = 100
    assert right.m_max == pytest.approx(left.m_max)
    assert right.defl_max == pytest.approx(left.defl_max, rel=1e-6)
    assert right.defl_max == pytest.approx((2.0 / 12) * 120**4 / (8 * E * IX), rel=1e-4)


def test_overhang_reactions_and_negative_moment():
    beam = BeamInput(length=20, support="simple", support_a=0, support_b=16)
    res = analyze(beam, [], [UniformLoad(1.0, 0, 20)], E, IX)
    assert res.reactions.forces == pytest.approx([7.5, 12.5])
    # Hogging moment over the right support is -w a^2 / 2 with a = 4 ft.
    idx = list(res.x).index(16.0)
    assert res.moment[idx] == pytest.approx(-8.0)
    assert res.moment[-1] == pytest.approx(0.0, abs=1e-9)
    assert res.deflection[idx] == pytest.approx(0.0, abs=1e-6)


def test_cb_for_uniform_load_simple_span():
    beam = BeamInput(length=20, support="simple", support_a=0, support_b=20)
    res = analyze(beam, [], [UniformLoad(1.0, 0, 20)], E, IX)
    # AISC Table 3-1: Cb = 1.14 for a simply supported uniformly loaded beam
    # braced only at the ends.
    assert compute_cb(res, 0, 20) == pytest.approx(1.14, abs=0.005)
