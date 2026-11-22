from collections import defaultdict


def partition(start, end, spans, scheduled):
    events = defaultdict(list, {start: [], end: []})
    for index, span in enumerate(spans):
        low, high = max(start, span["from_m"]), min(end, span["to_m"])
        if low < high:
            events[low].append((True, index))
            events[high].append((False, index))
    active = {"covered": set(), "unknown": set()}
    output = []
    cursor = start
    for point in sorted(events):
        if cursor < point:
            kind = "covered" if active["covered"] else "unknown" if active["unknown"] or not scheduled else "pending"
            indices = active[kind] if kind in active else set()
            if output and output[-1]["kind"] == kind:
                output[-1]["to_m"] = point
                output[-1]["references"].update(indices)
            else:
                output.append({"from_m": cursor, "to_m": point, "kind": kind, "references": set(indices)})
        for enter, index in events[point]:
            bucket = active[spans[index]["kind"]]
            bucket.add(index) if enter else bucket.remove(index)
        cursor = point
    return [{**row, "m": row["to_m"] - row["from_m"],
             "references": [spans[index] for index in sorted(row["references"])]} for row in output]
