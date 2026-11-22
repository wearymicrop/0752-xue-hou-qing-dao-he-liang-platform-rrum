from app.records import group_by, integer, issue, report, token
from app.source import lines


def parse(record):
    raw = record["raw"]
    axis = raw.get("axis")
    length, start, end = (raw.get(key) for key in ("length_m", "from_m", "to_m"))
    if (not token(raw.get("road")) or not token(raw.get("name")) or raw.get("direction") not in ("+", "-")
            or not isinstance(axis, list) or len(axis) != 4
            or any(not integer(value, -100_000, 100_000) for value in axis)
            or axis[:2] == axis[2:] or not all(integer(value) for value in (length, start, end))
            or not 0 <= start < end <= length <= 100_000):
        return None
    return {**record, **{key: raw[key] for key in ("road", "name", "direction", "axis", "length_m", "from_m", "to_m")}}


def build(source, _sections):
    valid, problems = [], []
    for record in lines(source, "roads"):
        row = parse(record)
        if row is None:
            problems.append(issue(record, "ROAD_SCHEMA", "道路轴线、方向或责任区间无效"))
        else:
            valid.append(row)
    roads = []
    for group in group_by(valid, "road", "direction").values():
        signature = {(tuple(row["axis"]), row["length_m"], row["from_m"], row["to_m"]) for row in group}
        if len(signature) > 1:
            problems.extend(issue(row, "ROAD_CONFLICT", "同一行车方向的责任定义冲突") for row in group)
            continue
        roads.append(group[0])
        problems.extend(issue(row, "ROAD_DUPLICATE", "重复道路定义") for row in group[1:])
    return report(roads, problems, total_m=sum(row["to_m"] - row["from_m"] for row in roads))
