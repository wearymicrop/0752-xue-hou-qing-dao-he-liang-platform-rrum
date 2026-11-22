from app.records import group_by, issue, report
from app.source import lines
from .contract import parse


def ingest(source, _sections):
    parsed, problems = [], []
    last_time = {}
    late = []
    for record in lines(source, "points"):
        row = parse(record)
        if row is None:
            problems.append(issue(record, "POINT_SCHEMA", "定位坐标、时间、开关或方向无效"))
            continue
        vehicle, timestamp = row["vehicle"], row["t"]
        if timestamp < last_time.get(vehicle, timestamp):
            late.append(issue(record, "OUT_OF_ORDER", "按采集时间重新排序"))
        last_time[vehicle] = max(timestamp, last_time.get(vehicle, timestamp))
        parsed.append(row)
    output = []
    for group in group_by(parsed, "vehicle", "t").values():
        compare = {tuple(row[key] for key in ("road", "direction", "plow", "x", "y")) for row in group}
        if len(compare) > 1:
            problems.extend(issue(row, "POINT_CONFLICT", "同车同秒定位互斥") for row in group)
            output.append({**group[0], "blocked": True, "conflict_lines": [row["line"] for row in group]})
        else:
            output.append(group[0])
            problems.extend(issue(row, "POINT_DUPLICATE", "相同定位只采信一次") for row in group[1:])
    output.sort(key=lambda row: (row["vehicle"], row["t"]))
    return report(output, problems, late=late, input_count=len(source["points"]))
