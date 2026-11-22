from app.modules.m4_windows.intervals import clip_motion, combine
from app.modules.m4_windows.service import rule


def test_half_open_contact_has_no_distance():  # TRAP-23
    assert clip_motion({"t": 0, "m": 0}, {"t": 6, "m": 100}, 6, 7) is None


def test_exact_conservative_rounding():  # TRAP-10
    assert clip_motion({"t": 0, "m": 0}, {"t": 6, "m": 100}, 1, 5) == [17, 83]


def test_windows_unioned_without_doubling(dirty_result):  # TRAP-25
    assert combine([(100, 340), (0, 960), (960, 1000)]) == [[0, 1000]]
    matching = [row for row in dirty_result["windows"]["rows"] if row["line"] == 2]
    assert len(matching) == 1 and matching[0]["window_lines"] == [1, 8]


def test_gap_keeps_candidate_window(dirty_result):
    row = next(point for point in dirty_result["windows"]["rows"] if point["kind"] == "unknown")
    assert (row["from_m"], row["to_m"], row["vehicle"]) == (780, 950, "云扫-02")


def test_turned_vehicle_not_counted_wrong_way(dirty_result):
    assert dirty_result["windows"]["reasons"]["WRONG_WAY"] == 1
    assert not any(row["line"] == 3 for row in dirty_result["windows"]["rows"])


def test_declared_direction_change_breaks_span():
    point = {"road":"S01", "direction":"+", "plow":True, "m":400}
    assert rule(point, {**point,"direction":"-","m":300})[0] == "LANE_CHANGE"
