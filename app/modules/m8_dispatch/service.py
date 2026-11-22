from collections import Counter

from app.config import RULESET
from app.errors import DomainError

from .plan import DISPATCH_POLICY, build_tasks, collect, stitch


def check(reconcile, tasks):
    """A plan must be a strict partition of the merged pending mileage.

    Dropping, duplicating or inventing metres would send the morning shift to
    the wrong place, so a broken plan is fatal: the caller keeps the
    previously published list instead of replacing it with a wrong one.
    """
    pending = reconcile["totals"]["pending_m"]
    assigned = sum(task["responsibility_m"] for task in tasks)
    if assigned != pending:
        raise DomainError("DISPATCH_UNBALANCED", "派工里程与待扫差额不一致，保留旧版清单", 409)
    keys = [(stop["road"], stop["direction"], stop["from_m"], stop["to_m"])
            for task in tasks for stop in task["stops"]]
    if len(keys) != len(set(keys)):
        raise DomainError("DISPATCH_DUPLICATE", "同一待扫区间重复派工，保留旧版清单", 409)
    if any(stop["to_m"] <= stop["from_m"] for task in tasks for stop in task["stops"]):
        raise DomainError("DISPATCH_UNBALANCED", "派工区间不成立，保留旧版清单", 409)


def lanes(coverage, tasks):
    """Post-dispatch ledger, recalculated from the merged coverage parts.

    ``difference_before_m`` is the missed-sweep difference the night shift left
    behind (the merged pending metres).  ``assigned_m`` hands exactly those
    metres to vehicles; ``difference_after_m`` is what is still unassigned.
    ``responsibility_m`` is recomputed from the post-merge lane, so both
    figures move together whenever the coverage merge changes.
    """
    assigned = Counter()
    for task in tasks:
        for stop in task["stops"]:
            assigned[(stop["road"], stop["direction"])] += stop["m"]
    result = []
    for row in coverage:
        key = (row["road"], row["direction"])
        sums = Counter({kind: 0 for kind in ("covered", "pending", "unknown")})
        for part in row["parts"]:
            sums[part["kind"]] += part["m"]
        responsibility = row["to_m"] - row["from_m"]
        result.append({
            "road": row["road"], "name": row["name"], "direction": row["direction"],
            "responsibility_m": responsibility,
            "covered_m": sums["covered"], "pending_m": sums["pending"],
            "unknown_m": sums["unknown"],
            "assigned_m": assigned[key],
            "difference_before_m": sums["pending"],
            "difference_after_m": sums["pending"] - assigned[key],
            "difference_m": responsibility - sums["covered"] - sums["unknown"] - assigned[key],
        })
    return result


def dispatch(source, sections):
    coverage = sections["coverage"]["rows"]
    reconcile = sections["reconcile"]
    gaps, held, problems = collect(coverage)
    tasks = build_tasks(source["batch"], stitch(gaps))
    check(reconcile, tasks)
    ledger = lanes(coverage, tasks)
    assigned = sum(task["responsibility_m"] for task in tasks)
    totals = {
        "responsibility_m": sum(row["responsibility_m"] for row in ledger),
        "covered_m": sum(row["covered_m"] for row in ledger),
        "pending_m": reconcile["totals"]["pending_m"],
        "assigned_m": assigned,
        "difference_before_m": reconcile["totals"]["pending_m"],
        "difference_after_m": reconcile["totals"]["pending_m"] - assigned,
        "unknown_m": reconcile["totals"]["unknown_m"],
        "difference_m": sum(row["difference_m"] for row in ledger),
        "vehicles": len(tasks),
        "gaps": len(gaps),
        "transfer_m": sum(task["transfer_m"] for task in tasks),
    }
    return {
        "batch": source["batch"], "as_of": source["at"], "ruleset": RULESET,
        "policy": DISPATCH_POLICY, "tasks": tasks, "lanes": ledger, "held": held,
        "totals": totals, "issues": problems,
        "reasons": dict(sorted(Counter(item["code"] for item in problems).items())),
        "status": "READY" if tasks else "NOTHING_TO_DISPATCH",
    }
