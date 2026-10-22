import pytest

from beam_check_desk.checks import available, flexure, shear
from beam_check_desk.shapes import get_shape, load_shapes


def test_shape_table_loads_and_has_w18x50():
    s = get_shape("W18x50")
    assert s.zx == pytest.approx(101)
    assert s.h_tw == pytest.approx(45.2, abs=0.1)
    assert s.bf_2tf == pytest.approx(6.57, abs=0.02)
    assert len(load_shapes()) > 250


def test_w18x50_matches_aisc_manual_table_3_2():
    s = get_shape("W18X50")
    f = flexure(s, 50, 29000, lb_in=0, cb=1.0)
    assert available(f.mn, f.phi, f.omega, "LRFD") / 12 == pytest.approx(379, abs=1)  # phi*Mp = 379 kip-ft
    assert available(f.mn, f.phi, f.omega, "ASD") / 12 == pytest.approx(252, abs=1)
    assert f.lp / 12 == pytest.approx(5.83, abs=0.02)
    assert f.lr / 12 == pytest.approx(16.9, abs=0.1)
    v = shear(s, 50, 29000)
    assert v.phi == 1.0
    assert available(v.vn, v.phi, v.omega, "LRFD") == pytest.approx(192, abs=1)


def test_w18x50_inelastic_ltb_at_lb_10ft():
    # AISC Manual Table 3-2 (W18x50, Fy = 50): phi*Mp = 379, phi*Mr = 233 kip-ft,
    # Lp = 5.83 ft, Lr = 16.9 ft, so BF = 13.2 kips and
    # phi*Mn(10 ft) = 379 - 13.2 * (10 - 5.83) = 324 kip-ft with Cb = 1.
    s = get_shape("W18X50")
    f = flexure(s, 50, 29000, lb_in=120, cb=1.0)
    assert f.governing == "lateral-torsional buckling"
    assert 0.9 * f.mn / 12 == pytest.approx(324, abs=2)


def test_elastic_ltb_beyond_lr():
    s = get_shape("W18X50")
    f = flexure(s, 50, 29000, lb_in=25 * 12, cb=1.0)
    assert f.mn < 0.7 * 50 * s.sx
    assert "F2-3" in " ".join(f.notes)


def test_noncompact_flange_shape_uses_f3():
    # W6x15 has bf/2tf = 11.5, noncompact for Fy = 50 (limit 9.15).
    s = get_shape("W6X15")
    f = flexure(s, 50, 29000, lb_in=0, cb=1.0)
    assert f.flange_class == "noncompact"
    assert f.mn < 50 * s.zx
    assert f.governing == "flange local buckling"
