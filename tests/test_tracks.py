from app.modules.m2_tracks.service import ingest


def test_clean_tracks_all_accepted(clean_result):
    result = clean_result["tracks"]
    assert result["input_count"] == len(result["rows"]) == 40


def test_duplicate_at_same_instant_across_offsets(dirty_result):  # TRAP-11
    result = dirty_result["tracks"]
    repeated = next(row for row in result["issues"] if row["code"] == "POINT_DUPLICATE")
    assert repeated["raw"]["time"] == "2026-01-16T22:01:20Z"
    assert [row["line"] for row in result["rows"] if row["vehicle"] == "云扫-01"] == [1, 2, 3, 4]


def test_late_samples_are_sorted(clean):  # TRAP-13
    clean["points"][:2] = clean["points"][1::-1]
    result = ingest(clean, {})
    assert [row["line"] for row in result["rows"][:2]] == [2, 1]
    assert result["late"][0]["code"] == "OUT_OF_ORDER"


def test_conflicting_timestamp_keeps_barrier(dirty_result):
    rows = [row for row in dirty_result["tracks"]["rows"] if row.get("blocked")]
    assert len(rows) == 1 and len(rows[0]["conflict_lines"]) == 2


def test_sentinel_is_quarantined(dirty_result):  # TRAP-07
    row = next(item for item in dirty_result["tracks"]["issues"] if item["code"] == "POINT_SCHEMA")
    assert row["raw"]["x"] == "未知"


def test_switch_rejects_string_false(clean):
    clean["points"][0]["plow"] = "false"
    assert ingest(clean, {})["reasons"] == {"POINT_SCHEMA": 1}
