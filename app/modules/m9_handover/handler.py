"""Handover state for a published dispatch list.

The list itself lives (frozen) in the archive's ``dispatch`` section.  This
module only adds the mutable part: which vehicle has accepted, finished or
returned each task.  Reads always come from the stored plan, writes are
idempotent per (batch, task, status).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.errors import DomainError
from app.records import token
from app.store import STATUS_LABELS

router = APIRouter(prefix="/api/dispatch/plans")


@router.get("/{batch}")
def read(batch: str, request: Request):
    return request.app.state.ledger.dispatch_by_batch(batch)


@router.get("/{batch}/runs/{ident}")
def read_run(batch: str, ident: str, request: Request):
    return request.app.state.ledger.dispatch_for_run(ident, batch)


@router.post("/{batch}/handover")
def handover(batch: str, body: dict, request: Request):
    task = body.get("task_id")
    if not isinstance(task, str) or not task:
        raise DomainError("TASK_REQUIRED", "请指定交接任务")
    status = body.get("status")
    if status not in STATUS_LABELS:
        raise DomainError("BAD_STATUS", "交接状态无效")
    actor = body.get("actor")
    if not token(actor):
        raise DomainError("ACTOR_REQUIRED", "请输入交接人")
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > 200:
        raise DomainError("BAD_NOTE", "交接备注过长")
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    view, receipt = request.app.state.ledger.handover(
        batch, task, status, actor.strip(), note.strip(), at)
    return {**view, "receipt": receipt}
