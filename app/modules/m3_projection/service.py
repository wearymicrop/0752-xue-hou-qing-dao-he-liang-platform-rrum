from app.records import issue, report
from app.modules.m1_routes.geometry import locate

MAX_OFFSET_M = 28


def match(_source, sections):
    roads = {(row["road"], row["direction"]): row for row in sections["routes"]["rows"]}
    output, problems = [], []
    for point in sections["tracks"]["rows"]:
        road = roads.get((point["road"], point["direction"]))
        located = {**point, "m": None, "offset_m": None}
        if point.get("blocked"):
            problems.append(issue(point, "CONFLICT_POINT", "冲突定位处截断轨迹"))
        elif road is None:
            problems.append(issue(point, "UNKNOWN_LANE", "找不到对应道路方向"))
        else:
            meter, offset = locate(road, point["x"], point["y"])
            located["offset_m"] = str(round(offset, 2))
            if offset > MAX_OFFSET_M:
                problems.append(issue(located, "GPS_DRIFT", "定位超出道路吸附阈值"))
            else:
                located["m"] = meter
        output.append(located)
    return report(output, problems, tolerance_m=MAX_OFFSET_M, projected=sum(row["m"] is not None for row in output))
