from time import perf_counter_ns

from app.codec import digest
from app.errors import DomainError
from app.pipeline import evaluate
from app.records import token
from .manifest import create


def execute(ledger, source):
    """Evaluate a batch and publish its dispatch list in one transaction.

    The whole update is atomic: if evaluation, the replay digest check or the
    plan publication fails, the previously published task list (and its
    handover progress) stays readable and unchanged.
    """
    start = perf_counter_ns()
    result = evaluate(source)
    manifest = create(source, result, (perf_counter_ns() - start) // 1_000_000)
    snapshot = {"id": manifest["id"], "manifest": manifest, "result": result}
    saved, reused, publication = ledger.archive(
        manifest["id"], source, snapshot, result["dispatch"], manifest["generated_at"])
    return {**saved, "reused": reused, "dispatch": publication}


def rerun(ledger, ident):
    source, previous = ledger.read(ident)
    result = evaluate(source)
    if digest(result) != previous["manifest"]["digest"]:
        raise DomainError("REPLAY_MISMATCH", "重跑结果与归档不一致", 409)
    view, publication = ledger.publish_dispatch(
        ident, result["dispatch"], previous["manifest"]["generated_at"])
    return {**previous, "reused": True, "dispatch": publication, "plan": view}


def publish(ledger, ident):
    """(Re)publish the dispatch list for an archived run from its frozen input.

    This is the resume path: a first import that failed before the plan was
    written can be completed later without touching the run snapshot, and a
    second call with the same plan is a no-op.
    """
    source, previous = ledger.read(ident)
    result = evaluate(source)
    if digest(result) != previous["manifest"]["digest"]:
        raise DomainError("REPLAY_MISMATCH", "重算结果与归档不一致", 409)
    view, publication = ledger.publish_dispatch(
        ident, result["dispatch"], previous["manifest"]["generated_at"])
    return {"id": ident, "manifest": previous["manifest"], "plan": view,
            "dispatch": publication}


def sign(ledger, ident, body):
    _, previous = ledger.read(ident)
    if not token(body.get("reviewer")):
        raise DomainError("REVIEWER_REQUIRED", "请输入签收人")
    if previous["manifest"]["digest"] != body.get("digest"):
        raise DomainError("STALE_DIGEST", "摘要已变化，请重新打开凭证", 409)
    receipt = {"reviewer": body["reviewer"].strip(), "digest": body["digest"],
               "id": ident, "balance": previous["result"]["reconcile"]["status"]}
    return ledger.sign(ident, receipt)
