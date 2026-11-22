"""Turn proven sweeping gaps into a deterministic per-vehicle route plan.

Rules (see docs/DEPTH.md, DISP-01..04):

* A *gap* is one ``pending`` part of the coverage merge.  ``covered`` is
  already done and ``unknown`` has no usable evidence, so neither may enter
  the morning dispatch list.
* A gap is *short* when it is at most ``DISPATCH_MAX_GAP_M`` metres long.
  Long gaps are full jobs on their own and are never stitched to something
  else.
* Short gaps are stitched when the straight-line distance between the exit
  of the previous gap and the entry of the next one is at most
  ``DISPATCH_MAX_TRANSFER_M``.  That distance is the vehicle transfer
  mileage, so stitching nearby gaps removes a drive between two jobs.
* Stitching never rewrites a gap.  Every stop keeps its original road,
  direction and station interval; only the execution order changes.
* The greedy visit order is canonical (road, direction, from_m; exact
  rational distances with deterministic tie-breaks) so replaying the same
  batch yields exactly the same task list.
"""

from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

from app.codec import digest
from app.config import (
    DISPATCH_MAX_GAP_M,
    DISPATCH_MAX_TRANSFER_M,
    DISPATCH_POLICY_VERSION,
    DISPATCH_VEHICLE_PREFIX,
)

Precise = Fraction

DISPATCH_POLICY = {
    "version": DISPATCH_POLICY_VERSION,
    "max_gap_m": DISPATCH_MAX_GAP_M,
    "max_transfer_m": DISPATCH_MAX_TRANSFER_M,
    "eligible_kind": "pending",
    "stitch": "nearest-neighbour, canonical order",
    "statuses": ["ASSIGNED", "ACCEPTED", "DONE", "RETURNED"],
}


def point(road, meter):
    """Map a station value to the local metric axis without rounding."""
    x0, y0, x1, y1 = road["axis"]
    length = road["length_m"]

    def at(value):
        return (Precise(x0 * length + (x1 - x0) * value, length),
                Precise(y0 * length + (y1 - y0) * value, length))

    return at(meter)


def squared(left, right):
    return (right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2


def distance(left, right):
    return float(squared(left, right) ** Precise(1, 2))


def rounded(meters):
    return int(Decimal(str(meters)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def endpoint(value):
    return [round(float(value[0]), 3), round(float(value[1]), 3)]


def gap(road, part, index):
    """Describe one pending coverage part as an executable stop."""
    entry_m = part["from_m"] if road["direction"] == "+" else part["to_m"]
    exit_m = part["to_m"] if road["direction"] == "+" else part["from_m"]
    return {
        "road": road["road"],
        "name": road["name"],
        "direction": road["direction"],
        "from_m": part["from_m"],
        "to_m": part["to_m"],
        "m": part["m"],
        "part_index": index,
        "entry": endpoint(point(road, entry_m)),
        "exit": endpoint(point(road, exit_m)),
        "entry_m": entry_m,
        "exit_m": exit_m,
        "basis": {
            "table": "coverage",
            "road": road["road"],
            "name": road["name"],
            "direction": road["direction"],
            "route_line": road.get("line"),
            "part_index": index,
            "from_m": part["from_m"],
            "to_m": part["to_m"],
            "kind": "pending",
            "reason": "覆盖合并后的待扫区间",
            "references": part["references"],
            "ledger": {
                "responsibility_m": road["to_m"] - road["from_m"],
                "covered_m": sum(item["m"] for item in road["parts"] if item["kind"] == "covered"),
                "pending_m": sum(item["m"] for item in road["parts"] if item["kind"] == "pending"),
                "unknown_m": sum(item["m"] for item in road["parts"] if item["kind"] == "unknown"),
            },
        },
    }


def identity(item):
    return (item["road"], item["direction"], item["from_m"], item["to_m"])


def collect(coverage):
    """Return (gaps, held, issues).  Coverage order is kept for stable output."""
    gaps, held, issues, seen = [], [], [], set()
    for row in coverage:
        for index, part in enumerate(row["parts"]):
            if part["kind"] == "unknown":
                held.append({
                    "road": row["road"], "direction": row["direction"],
                    "from_m": part["from_m"], "to_m": part["to_m"],
                    "m": part["m"], "kind": "unknown",
                })
                issues.append({
                    "table": "coverage",
                    "road": row["road"], "direction": row["direction"],
                    "from_m": part["from_m"], "to_m": part["to_m"],
                    "code": "EVIDENCE_HELD",
                    "detail": "证据不足区间不进入派工清单",
                })
                continue
            if part["kind"] != "pending":
                continue
            item = gap(row, part, index)
            if identity(item) in seen:
                issues.append({
                    "table": "coverage",
                    "road": row["road"], "direction": row["direction"],
                    "from_m": part["from_m"], "to_m": part["to_m"],
                    "code": "DISPATCH_DUPLICATE",
                    "detail": "同一待扫区间只派工一次",
                })
                continue
            seen.add(identity(item))
            gaps.append(item)
    return gaps, held, issues


def short(item):
    return item["m"] <= DISPATCH_MAX_GAP_M


def stitch(gaps):
    """Greedy nearest-neighbour chaining with a canonical visit order.

    A route keeps extending while the preceding stop is short.  The next stop
    is the closest eligible short gap reachable within the transfer limit;
    ties break on road, direction and station so the result does not depend on
    input row order.
    """
    remaining = sorted(gaps, key=identity)
    limit = DISPATCH_MAX_TRANSFER_M ** 2
    routes = []
    while remaining:
        chain = [remaining.pop(0)]
        while short(chain[-1]):
            last = chain[-1]
            best = None
            for candidate in remaining:
                if not short(candidate):
                    continue
                travel = squared(last["exit"], candidate["entry"])
                if travel > limit:
                    continue
                rank = (travel, candidate["road"], candidate["direction"],
                        candidate["from_m"], candidate["to_m"])
                if best is None or rank < best[0]:
                    best = (rank, travel, candidate)
            if best is None:
                break
            remaining.remove(best[2])
            transfer_m = rounded(distance(last["exit"], best[2]["entry"]))
            chain.append({**best[2], "transfer_m": transfer_m})
        routes.append(chain)
    return routes


def task_id(batch, stops):
    return digest({"batch": batch,
                   "stops": [list(identity(stop)) for stop in stops]})


def vehicle_name(index):
    return f"{DISPATCH_VEHICLE_PREFIX}-{index:02d}"


def build_tasks(batch, routes):
    tasks = []
    for number, chain in enumerate(routes, 1):
        stops = []
        for sequence, item in enumerate(chain, 1):
            stops.append({**item, "seq": sequence, "transfer_m": item.get("transfer_m", 0)})
        total = sum(stop["m"] for stop in stops)
        moved = sum(stop["transfer_m"] for stop in stops)
        tasks.append({
            "task_id": task_id(batch, stops),
            "vehicle": vehicle_name(number),
            "status": "ASSIGNED",
            "status_label": "已派工",
            "receipt": None,
            "sequence": number,
            "stops": stops,
            "gap_count": len(stops),
            "responsibility_m": total,
            "total_m": total,
            "transfer_m": moved,
            "basis": {
                "source": "coverage.parts[kind=pending]",
                "policy": {"max_gap_m": DISPATCH_MAX_GAP_M,
                           "max_transfer_m": DISPATCH_MAX_TRANSFER_M},
                "stops": [stop["basis"] for stop in stops],
            },
        })
    return tasks
