from app.clock import instant
from app.records import integer, token


def parse(record):
    raw = record["raw"]
    if (not token(raw.get("vehicle")) or not token(raw.get("road")) or raw.get("direction") not in ("+", "-")
            or type(raw.get("plow")) is not bool
            or any(not integer(raw.get(key), -100_000, 100_000) for key in ("x", "y"))):
        return None
    try:
        timestamp = instant(raw.get("time"))
    except ValueError:
        return None
    return {**record, "t": timestamp, **{key: raw[key] for key in ("vehicle", "road", "direction", "plow", "x", "y")}}
