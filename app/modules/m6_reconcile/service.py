from app.records import report
from .ledger import totals_for


def reconcile(_source, sections):
    ledger = []
    for row in sections["coverage"]["rows"]:
        ledger.append({"road": row["road"], "direction": row["direction"], "name": row["name"],
                       "duplicate_m": row["duplicate_m"], **totals_for(row)})
    fields = ("responsibility_m", "covered_m", "pending_m", "unknown_m", "difference_m", "duplicate_m")
    totals = {field: sum(row[field] for row in ledger) for field in fields}
    totals["lanes"] = len(ledger)
    matched = bool(ledger) and all(row["continuous"] and row["difference_m"] == 0 for row in ledger)
    exceptions = [issue for name in ("routes", "tracks", "projection", "windows", "coverage")
                  for issue in sections[name]["issues"]]
    return report(ledger, exceptions, totals=totals, status="MATCHED" if matched else "CHECK_REQUIRED")
