from fractions import Fraction
from math import ceil, floor


def combine(spans):
    result = []
    for start, end in sorted(spans):
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return result


def clip_motion(left, right, start, end):
    first = max(start, left["t"])
    last = min(end, right["t"])
    if first >= last:
        return None
    slope = Fraction(right["m"] - left["m"], right["t"] - left["t"])
    meters = [left["m"] + slope * (at - left["t"]) for at in (first, last)]
    low, high = ceil(min(meters)), floor(max(meters))
    return [low, high] if low < high else None
