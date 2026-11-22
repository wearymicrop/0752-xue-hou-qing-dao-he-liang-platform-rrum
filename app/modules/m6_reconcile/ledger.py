KINDS = {"covered": "covered_m", "pending": "pending_m", "unknown": "unknown_m"}


def totals_for(row):
    totals = dict.fromkeys(KINDS.values(), 0)
    cursor = row["from_m"]
    continuous = True
    for part in row["parts"]:
        start, end = part["from_m"], part["to_m"]
        if start != cursor or end <= start or part["m"] != end - start:
            continuous = False
        totals[KINDS[part["kind"]]] += end - start
        cursor = end
    responsibility = row["to_m"] - row["from_m"]
    return {**totals, "responsibility_m": responsibility, "difference_m": responsibility - sum(totals.values()),
            "continuous": continuous and cursor == row["to_m"]}
