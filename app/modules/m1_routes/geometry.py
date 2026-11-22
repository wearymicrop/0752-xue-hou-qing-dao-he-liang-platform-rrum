from decimal import Decimal, ROUND_HALF_UP, localcontext


def locate(road, x, y):
    ax, ay, bx, by = road["axis"]
    dx, dy = bx - ax, by - ay
    px, py = x - ax, y - ay
    dot = px * dx + py * dy
    norm = dx * dx + dy * dy
    with localcontext() as context:
        context.prec = 32
        ratio = min(Decimal(1), max(Decimal(0), Decimal(dot) / norm))
        distance = ((px - ratio * dx)**2 + (py - ratio * dy)**2).sqrt()
        meter = int((ratio * road["length_m"]).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return meter, distance
