from .modules.m1_routes.service import build
from .modules.m2_tracks.service import ingest
from .modules.m3_projection.service import match
from .modules.m4_windows.service import assess
from .modules.m5_coverage.service import merge
from .modules.m6_reconcile.service import reconcile

TABLES = ("roads", "points", "windows")
STAGES = (("routes", build), ("tracks", ingest), ("projection", match),
          ("windows", assess), ("coverage", merge), ("reconcile", reconcile))
