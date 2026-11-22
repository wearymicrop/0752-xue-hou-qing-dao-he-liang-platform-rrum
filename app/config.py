import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = "雪后清道核量台"
PROJECT = "gb-0752"
RULESET = "gb-0752/1.0"
SIGNATURE_TITLE = "工单凭证"
SAMPLES = {"dirty": "现场样例", "clean": "干净样例"}
MAX_ROWS = 2500


def database_path():
    return Path(os.getenv("WORKBENCH_DB", ROOT / "instance" / "workbench.sqlite3"))
