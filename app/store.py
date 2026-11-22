from contextlib import contextmanager
import json
import sqlite3

from .codec import canonical, digest
from .errors import DomainError


class Ledger:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, snapshot TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signatures (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id), receipt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dispatch_plans (
                    batch TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    digest TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    published_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dispatch_handovers (
                    batch TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    actor TEXT,
                    note TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (batch, task_id)
                );
                CREATE TABLE IF NOT EXISTS dispatch_events (
                    batch TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT NOT NULL,
                    at TEXT NOT NULL,
                    UNIQUE (batch, task_id, status, actor, note)
                );
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # -- runs --------------------------------------------------------------
    def archive(self, ident, source, snapshot, plan, now):
        """Write the run and its dispatch list in one transaction.

        A failure anywhere (digest replay check, plan replacement, storage)
        rolls the whole transaction back, so the previously published task
        list and its handover progress stay exactly as they were.
        """
        source_data = canonical(source)
        snapshot_data = canonical(snapshot)
        plan_data = canonical(plan) if plan is not None else None
        with self.connect() as connection:
            inserted = connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (ident, source_data, snapshot_data),
            )
            row = connection.execute("SELECT snapshot FROM runs WHERE id = ?", (ident,)).fetchone()
            saved = json.loads(row[0])
            if saved["manifest"]["digest"] != snapshot["manifest"]["digest"]:
                raise DomainError("REPLAY_MISMATCH", "重算摘要不一致，请复核规则版本", 409)
            publication = None
            if plan is not None:
                publication = self._publish(connection, plan["batch"], ident, plan, plan_data, now)
            return saved, inserted.rowcount == 0, publication

    def read(self, ident):
        with self.connect() as connection:
            row = connection.execute("SELECT source, snapshot FROM runs WHERE id = ?", (ident,)).fetchone()
            if row is None:
                raise DomainError("RUN_NOT_FOUND", "找不到此运行", 404)
            sign = connection.execute("SELECT receipt FROM signatures WHERE run_id = ?", (ident,)).fetchone()
            snapshot = json.loads(row[1])
            return json.loads(row[0]), {**snapshot, "signature": json.loads(sign[0]) if sign else None}

    def recent(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT snapshot FROM runs ORDER BY rowid DESC LIMIT 30").fetchall()
            return [json.loads(row[0])["manifest"] for row in rows]

    def sign(self, ident, receipt):
        data = canonical(receipt)
        with self.connect() as connection:
            inserted = connection.execute(
                "INSERT INTO signatures VALUES (?, ?) ON CONFLICT(run_id) DO NOTHING", (ident, data))
            saved = connection.execute("SELECT receipt FROM signatures WHERE run_id = ?", (ident,)).fetchone()[0]
            if saved != data:
                raise DomainError("ALREADY_SIGNED", "此运行已由他人签收", 409)
            return {**json.loads(saved), "reused": inserted.rowcount == 0}

    # -- dispatch plan -----------------------------------------------------
    def _publish(self, connection, batch, run_id, plan, data, now):
        """Freeze a task list for a batch, inside the caller's transaction.

        Replaying the same plan is a no-op: task ids and order stay untouched.
        A genuinely different plan replaces the list, and handover rows are
        reconciled per task id so unchanged tasks keep their progress while
        tasks that no longer exist drop out.
        """
        stamp = digest(plan)
        row = connection.execute(
            "SELECT digest FROM dispatch_plans WHERE batch = ?", (batch,)).fetchone()
        if row is not None and row[0] == stamp:
            return {"reused": True, "replaced": False, "digest": stamp}
        connection.execute(
            "INSERT INTO dispatch_plans VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(batch) DO UPDATE SET run_id = excluded.run_id, "
            "digest = excluded.digest, snapshot = excluded.snapshot, "
            "published_at = excluded.published_at",
            (batch, run_id, stamp, data, now),
        )
        kept = [task["task_id"] for task in plan["tasks"]]
        if kept:
            marks = ",".join("?" for _ in kept)
            for table in ("dispatch_handovers", "dispatch_events"):
                connection.execute(
                    f"DELETE FROM {table} WHERE batch = ? AND task_id NOT IN ({marks})",
                    (batch, *kept))
        else:
            for table in ("dispatch_handovers", "dispatch_events"):
                connection.execute(f"DELETE FROM {table} WHERE batch = ?", (batch,))
        return {"reused": False, "replaced": row is not None, "digest": stamp}

    def publish_dispatch(self, ident, plan, now):
        """Publish (or republish) a plan for an already archived run.

        Used by the resume path and by reruns.  The transaction either writes
        the new list and prunes stale handover rows together, or leaves the
        old list untouched.
        """
        with self.connect() as connection:
            row = connection.execute("SELECT 1 FROM runs WHERE id = ?", (ident,)).fetchone()
            if row is None:
                raise DomainError("RUN_NOT_FOUND", "找不到此运行", 404)
            publication = self._publish(
                connection, plan["batch"], ident, plan, canonical(plan), now)
            return self._dispatch_view(connection, plan["batch"], plan), publication

    def dispatch_for_run(self, ident, batch):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM dispatch_plans WHERE batch = ?", (batch,)).fetchone()
            if row is None:
                raise DomainError("DISPATCH_NOT_FOUND", "此批次尚未生成派工清单", 404)
            if row[1] != ident:
                # An older, superseded list must never be handed to the morning
                # shift under a newer run id.
                raise DomainError("DISPATCH_SUPERSEDED", "该运行的清单已被新版本替换", 409)
            return self._dispatch_view(connection, batch, json.loads(row[3]))

    def dispatch_by_batch(self, batch):
        with self.connect() as connection:
            row = connection.execute("SELECT snapshot FROM dispatch_plans WHERE batch = ?", (batch,)).fetchone()
            if row is None:
                raise DomainError("DISPATCH_NOT_FOUND", "此批次尚未生成派工清单", 404)
            return self._dispatch_view(connection, batch, json.loads(row[0]))

    def _dispatch_view(self, connection, batch, plan):
        handovers = {row[0]: {"status": row[1], "actor": row[2], "note": row[3], "updated_at": row[4]}
                     for row in connection.execute(
                         "SELECT task_id, status, actor, note, updated_at FROM dispatch_handovers WHERE batch = ?",
                         (batch,))}
        tasks = []
        for task in plan["tasks"]:
            state = handovers.get(task["task_id"])
            status = state["status"] if state else "ASSIGNED"
            tasks.append({
                **task,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "handover": state or {"status": "ASSIGNED", "status_label": STATUS_LABELS["ASSIGNED"],
                                      "actor": None, "note": None, "updated_at": None},
            })
        events = [{"task_id": row[0], "status": row[1], "status_label": STATUS_LABELS[row[1]],
                   "actor": row[2], "note": row[3], "at": row[4]} for row in connection.execute(
            "SELECT task_id, status, actor, note, at FROM dispatch_events WHERE batch = ? ORDER BY rowid", (batch,))]
        return {**plan, "batch": batch, "tasks": tasks, "events": events,
                "summary": summary(tasks)}

    def handover(self, batch, task_id, status, actor, note, at):
        """Move one task to a new handover status, idempotently."""
        with self.connect() as connection:
            row = connection.execute("SELECT snapshot FROM dispatch_plans WHERE batch = ?", (batch,)).fetchone()
            if row is None:
                raise DomainError("DISPATCH_NOT_FOUND", "此批次尚未生成派工清单", 404)
            plan = json.loads(row[0])
            if not any(item["task_id"] == task_id for item in plan["tasks"]):
                raise DomainError("TASK_NOT_FOUND", "清单中没有此任务", 404)
            current = connection.execute(
                "SELECT status FROM dispatch_handovers WHERE batch = ? AND task_id = ?",
                (batch, task_id)).fetchone()
            current = current[0] if current else "ASSIGNED"
            reused = status == current
            if not reused:
                if status not in TRANSITIONS.get(current, frozenset()):
                    raise DomainError("BAD_TRANSITION", f"{STATUS_LABELS[current]}不能直接变为"
                                      f"{STATUS_LABELS.get(status, status)}", 409)
                connection.execute(
                    "INSERT INTO dispatch_handovers VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(batch, task_id) DO UPDATE SET status = excluded.status, "
                    "actor = excluded.actor, note = excluded.note, updated_at = excluded.updated_at",
                    (batch, task_id, status, actor, note, at),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO dispatch_events VALUES (?, ?, ?, ?, ?, ?)",
                    (batch, task_id, status, actor, note or "", at),
                )
            return self._dispatch_view(connection, batch, plan), {"reused": reused, "status": status}


STATUS_LABELS = {
    "ASSIGNED": "已派工",
    "ACCEPTED": "已领取",
    "DONE": "已完成",
    "RETURNED": "已退回",
}

TRANSITIONS = {
    "ASSIGNED": frozenset({"ACCEPTED", "RETURNED"}),
    "ACCEPTED": frozenset({"DONE", "RETURNED"}),
    "RETURNED": frozenset({"ACCEPTED"}),
    "DONE": frozenset(),
}


def summary(tasks):
    counts = {status: 0 for status in STATUS_LABELS}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    total = sum(task["responsibility_m"] for task in tasks)
    accepted = sum(task["responsibility_m"] for task in tasks
                   if task["status"] in {"ACCEPTED", "DONE"})
    done = sum(task["responsibility_m"] for task in tasks if task["status"] == "DONE")
    return {"tasks": len(tasks), "statuses": counts, "assigned_m": total,
            "accepted_m": accepted, "done_m": done,
            "outstanding_m": total - done}
