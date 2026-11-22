import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = "雪后清道核量台"
PROJECT = "gb-0752"
RULESET = "gb-0752/1.1"
SIGNATURE_TITLE = "工单凭证"
SAMPLES = {"dirty": "现场样例", "clean": "干净样例"}
MAX_ROWS = 2500

# Dispatch (接班派工) thresholds.  A gap longer than DISPATCH_MAX_GAP_M is a
# full-day job and is never stitched; gaps are only chained when a vehicle can
# reach the next entry within DISPATCH_MAX_TRANSFER_M.
DISPATCH_MAX_GAP_M = 350
DISPATCH_MAX_TRANSFER_M = 250
DISPATCH_VEHICLE_PREFIX = "早班"
DISPATCH_POLICY_VERSION = "dispatch/1"


def database_path():
    return Path(os.getenv("WORKBENCH_DB", ROOT / "instance" / "workbench.sqlite3"))
