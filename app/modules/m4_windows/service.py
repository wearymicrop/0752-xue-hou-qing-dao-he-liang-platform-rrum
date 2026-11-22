from app.clock import instant, utc
from app.modules.m3_projection.anchors import adjacent
from app.records import group_by, issue, report
from app.source import lines
from .intervals import clip_motion, combine

MAX_GAP_S = 150


def schedule(source, roads):
    result, problems = [], []
    keys = {(road["road"], road["direction"]) for road in roads}
    for row in lines(source, "windows"):
        raw = row["raw"]
        road, direction = raw.get("road"), raw.get("direction")
        try:
            start, end = instant(raw.get("start")), instant(raw.get("end"))
        except ValueError:
            start = end = 0
        if (not isinstance(road, str) or not isinstance(direction, str)
                or (road, direction) not in keys or not 0 < end - start <= 86400):
            problems.append(issue(row, "WINDOW_SCHEMA", "作业窗口不成立或没有对应道路"))
            continue
        result.append({**row, "road": road, "direction": direction, "start": start, "end": end})
    return result, problems


def rule(left, right):
    if (left["road"], left["direction"]) != (right["road"], right["direction"]):
        return "LANE_CHANGE", "方向或道路切换处截断"
    if not left["plow"]:
        return "PLOW_OFF", "此段车辆未开启作业"
    if left["m"] is None or right["m"] is None:
        return "NO_ANCHOR", "此段缺少可信定位端点"
    motion = (right["m"] - left["m"]) * (1 if left["direction"] == "+" else -1)
    if motion <= 0:
        return "WRONG_WAY" if motion < 0 else "STATIONARY", "此段未沿申报方向前进"
    return None, None


def assess(source, sections):
    rows, problems = schedule(source, sections["routes"]["rows"])
    windows = group_by(rows, "road", "direction")
    output = []
    for left, right in adjacent(sections["projection"]["rows"]):
        key = (left["road"], left["direction"])
        evidence = {"table": "points", "line": left["line"], "end_line": right["line"],
                    "vehicle": left["vehicle"], "road": key[0], "direction": key[1]}
        code, detail = rule(left, right)
        if code:
            problems.append(issue(evidence, code, detail))
            continue
        accepted = windows.get(key, [])
        spans = combine((row["start"], row["end"]) for row in accepted)
        gap = right["t"] - left["t"] > MAX_GAP_S
        count = 0
        for start, end in spans:
            clipped = clip_motion(left, right, start, end)
            if clipped is None:
                continue
            count += 1
            output.append({**evidence, "from_m": clipped[0], "to_m": clipped[1],
                           "start": utc(max(start, left["t"])), "end": utc(min(end, right["t"])),
                           "window_lines": [row["line"] for row in accepted if
                                            max(row["start"], left["t"], start) < min(row["end"], right["t"], end)],
                           "kind": "unknown" if gap else "covered"})
        if gap:
            problems.append(issue(evidence, "GPS_GAP", "两定位点间隔超过 150 秒"))
        if not count:
            problems.append(issue(evidence, "OUTSIDE_WINDOW", "未与作业窗口形成有效距离"))
    return report(output, problems, schedules=rows, max_gap_s=MAX_GAP_S)
