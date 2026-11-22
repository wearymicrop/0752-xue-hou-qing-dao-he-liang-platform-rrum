from itertools import pairwise

from app.records import group_by


def adjacent(rows):
    for group in group_by(rows, "vehicle").values():
        yield from pairwise(group)
