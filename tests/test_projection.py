from decimal import Decimal

from app.modules.m1_routes.geometry import locate
from app.modules.m3_projection.service import match


def test_along_route_reference(clean_result):
    assert clean_result["projection"]["rows"][1]["m"] == 250


def test_offset_is_measured_to_finite_axis(clean):
    assert locate(clean["roads"][0], -12, 0) == (0, Decimal(12))


def test_calibrated_meter_scale(clean):
    assert locate(clean["roads"][6], 455, 230) == (420, Decimal(0))


def test_drift_no_usable_anchor(dirty_result):
    rejected = next(row for row in dirty_result["projection"]["issues"] if row["code"] == "GPS_DRIFT")
    assert rejected["offset_m"] == "65.00" and rejected["m"] is None


def test_unknown_direction_does_not_borrow_axis(clean_result):  # TRAP-21
    point = {**clean_result["tracks"]["rows"][0], "road": "S02", "direction": "-"}
    assert match(None, {"routes": clean_result["routes"], "tracks": {"rows": [point]}})["reasons"] == {"UNKNOWN_LANE": 1}


def test_conflict_does_not_project(dirty_result):
    assert next(row for row in dirty_result["projection"]["rows"] if row.get("blocked"))["m"] is None
