from app.modules.m1_routes.service import build


def test_lane_meter_total(clean_result):
    assert clean_result["routes"]["total_m"] == 5265


def test_reverse_lane_is_separate(clean_result):
    rows = [row for row in clean_result["routes"]["rows"] if row["road"] == "S01"]
    assert [row["direction"] for row in rows] == ["+", "-"]


def test_duplicate_road_does_not_add_length(dirty_result):
    assert dirty_result["routes"]["reasons"] == {"ROAD_DUPLICATE": 1, "ROAD_SCHEMA": 1}
    assert dirty_result["routes"]["total_m"] == 5265


def test_conflicting_definitions_all_quarantined(clean):  # TRAP-14
    clean["roads"].append({**clean["roads"][0], "to_m": 900})
    result = build(clean, {})
    assert result["reasons"] == {"ROAD_CONFLICT": 2}
    assert result["total_m"] == 4265


def test_road_interval_respects_calibrated_length(clean):
    clean["roads"][0]["to_m"] = 1001
    assert build(clean, {})["issues"][0]["line"] == 1


def test_empty_routes_yields_zero(clean):
    clean["roads"] = []
    assert build(clean, {})["total_m"] == 0
