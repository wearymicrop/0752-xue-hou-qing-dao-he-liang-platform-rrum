from app.modules.m6_reconcile.ledger import totals_for
from app.pipeline import evaluate


def test_dirty_business_totals(dirty_result):
    assert dirty_result["reconcile"]["totals"] == {"responsibility_m":5265,"covered_m":3049,
        "pending_m":1546,"unknown_m":670,"difference_m":0,"duplicate_m":120,"lanes":8}


def test_clean_all_meters_covered(clean_result):
    totals = clean_result["reconcile"]["totals"]
    assert totals["responsibility_m"] == totals["covered_m"] == 5265


def test_reverse_lane_has_own_ledger(dirty_result):
    assert dirty_result["reconcile"]["rows"][1]["covered_m"] == 300


def test_different_distributions_with_equal_sums_detected():
    row = {"from_m":0,"to_m":30,"parts":[{"from_m":5,"to_m":35,"m":30,"kind":"covered"}]}
    assert totals_for(row)["difference_m"] == 0 and not totals_for(row)["continuous"]


def test_empty_ledger_has_explicit_state(clean):  # TRAP-18
    clean["roads"] = []
    result = evaluate(clean)["reconcile"]
    assert result["status"] == "CHECK_REQUIRED" and result["totals"]["lanes"] == 0


def test_each_lane_conserves_full_length(dirty_result):
    for row in dirty_result["reconcile"]["rows"]:
        assert row["responsibility_m"] == row["covered_m"] + row["pending_m"] + row["unknown_m"]
