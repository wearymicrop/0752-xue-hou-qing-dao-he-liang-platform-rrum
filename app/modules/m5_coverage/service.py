from app.records import group_by, issue, report
from .sweep import partition


def merge(_source, sections):
    work = sections["windows"]
    spans = group_by(work["rows"], "road", "direction")
    scheduled = group_by(work["schedules"], "road", "direction")
    output, problems = [], []
    for road in sections["routes"]["rows"]:
        key = road["road"], road["direction"]
        has_schedule = key in scheduled
        start, end = road["from_m"], road["to_m"]
        evidence = spans.get(key, [])
        parts = partition(start, end, evidence, has_schedule)
        if not has_schedule:
            problems.append(issue(road, "MISSING_WINDOW", "方向未登记有效窗口"))
        raw_m = sum(max(0, min(end, span["to_m"]) - max(start, span["from_m"]))
                    for span in evidence if span["kind"] == "covered")
        covered_m = sum(part["m"] for part in parts if part["kind"] == "covered")
        output.append({**road, "parts": parts, "raw_covered_m": raw_m, "duplicate_m": raw_m - covered_m})
    return report(output, problems)
