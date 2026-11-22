from app.modules.m5_coverage.sweep import partition


def test_two_vehicles_overlap_only_once(dirty_result):  # TRAP-19
    row = dirty_result["coverage"]["rows"][0]
    assert row["raw_covered_m"] == 900 and row["duplicate_m"] == 120
    assert [part["m"] for part in row["parts"]] == [780,170,50]


def test_proven_overlap_overrides_gap():
    result = partition(0, 100, [{"from_m":10,"to_m":80,"kind":"unknown"},
                               {"from_m":20,"to_m":90,"kind":"covered"}], True)
    assert [(part["kind"], part["m"]) for part in result] == [("pending",10),("unknown",10),("covered",70),("pending",10)]


def test_boundary_is_clipped_to_responsibility(dirty_result):
    row = next(item for item in dirty_result["coverage"]["rows"] if item["road"] == "S04")
    assert row["parts"][0]["from_m"] == 80 and row["parts"][0]["m"] == 380


def test_missing_schedule_is_unknown(dirty_result):
    row = next(item for item in dirty_result["coverage"]["rows"] if item["road"] == "S05")
    assert [(part["kind"],part["m"]) for part in row["parts"]] == [("unknown",500)]


def test_evidence_preserves_both_active_sources(dirty_result):
    first = dirty_result["coverage"]["rows"][0]["parts"][0]
    assert {item["vehicle"] for item in first["references"]} == {"云扫-01", "云扫-02"}


def test_adjacent_spans_merge_into_one():
    result = partition(0, 100, [{"from_m":0,"to_m":40,"kind":"covered"},
                               {"from_m":40,"to_m":100,"kind":"covered"}], True)
    assert len(result) == 1 and result[0]["m"] == 100
