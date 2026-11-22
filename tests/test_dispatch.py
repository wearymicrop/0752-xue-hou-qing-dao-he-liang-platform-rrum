import pytest
from fastapi.testclient import TestClient

from app.errors import DomainError
from app.main import create_app
from app.modules.m8_dispatch import service as dispatch_service
from app.modules.m8_dispatch.plan import collect, identity, stitch
from app.modules.m8_dispatch.service import dispatch


def parts(result):
    return [part for row in result["coverage"]["rows"] for part in row["parts"]]


def test_only_pending_parts_enter_the_list(dirty_result):
    plan = dispatch({"batch": "雪勤-0117-现场", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    stops = [stop for task in plan["tasks"] for stop in task["stops"]]
    assert {stop["basis"]["kind"] for stop in stops} == {"pending"}
    pending = [part for part in parts(dirty_result) if part["kind"] == "pending"]
    assert len(stops) == len(pending)
    assert sum(stop["m"] for stop in stops) == dirty_result["reconcile"]["totals"]["pending_m"]


def test_covered_and_unknown_never_dispatched(dirty_result):
    plan = dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    dispatched = {identity(stop) for task in plan["tasks"] for stop in task["stops"]}
    for row in dirty_result["coverage"]["rows"]:
        for part in row["parts"]:
            if part["kind"] != "pending":
                assert (row["road"], row["direction"], part["from_m"], part["to_m"]) not in dispatched
    # S05 has no window at all: it is evidence-less, so it must not be swept.
    assert all(stop["road"] != "S05" for task in plan["tasks"] for stop in task["stops"])
    assert any(item["road"] == "S05" for item in plan["held"])


def test_each_stop_keeps_road_direction_and_interval(dirty_result):
    plan = dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    source = {(row["road"], row["direction"], part["from_m"], part["to_m"])
              for row in dirty_result["coverage"]["rows"] for part in row["parts"]
              if part["kind"] == "pending"}
    for task in plan["tasks"]:
        assert task["stops"]
        for stop in task["stops"]:
            assert stop["direction"] in ("+", "-")
            assert (stop["road"], stop["direction"], stop["from_m"], stop["to_m"]) in source
            assert stop["to_m"] > stop["from_m"] and stop["m"] == stop["to_m"] - stop["from_m"]


def test_stops_are_ordered_by_precise_axis(dirty_result):
    plan = dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    for task in plan["tasks"]:
        assert [stop["seq"] for stop in task["stops"]] == list(range(1, len(task["stops"]) + 1))
        assert task["stops"][0]["transfer_m"] == 0


def test_stitch_reduces_transfers_for_neighbours(dirty_result):
    gaps, _, _ = collect(dirty_result["coverage"]["rows"])
    plan = dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    routes = [task for task in plan["tasks"] if len(task["stops"]) > 1]
    assert routes, "相邻短缺口应被拼接"
    # Every stitched hop still fits the transfer limit.
    for task in routes:
        for previous, following in zip(task["stops"], task["stops"][1:]):
            assert following["transfer_m"] <= plan["policy"]["max_transfer_m"]
            assert following["transfer_m"] >= 0
    assert len(plan["tasks"]) < len(gaps)
    assert plan["totals"]["transfer_m"] > 0


def test_long_gap_is_not_stitched():
    class Road(dict):
        pass
    road = {"road": "R", "name": "长段", "direction": "+", "axis": [0, 0, 1000, 0],
            "length_m": 1000, "from_m": 0, "to_m": 1000}
    short = {"from_m": 0, "to_m": 50, "m": 50, "kind": "pending", "references": []}
    long = {"from_m": 100, "to_m": 500, "m": 400, "kind": "pending", "references": []}
    gaps, _, _ = collect([{**road, "parts": [short, long]}])
    routes = stitch(gaps)
    assert [len(route) for route in routes] == [1, 1]


def test_replay_is_bit_identical(dirty_result):
    first = dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    second = dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    assert first == second
    assert [task["task_id"] for task in first["tasks"]] == [task["task_id"] for task in second["tasks"]]


def test_lane_difference_moves_with_merge(dirty, clean):
    from app.pipeline import evaluate
    dirty_plan = evaluate(dirty)["dispatch"]
    clean_plan = evaluate(clean)["dispatch"]
    assert dirty_plan["totals"]["difference_before_m"] == 1546
    assert dirty_plan["totals"]["difference_after_m"] == 0
    assert clean_plan["totals"]["difference_before_m"] == 0
    assert clean_plan["totals"]["assigned_m"] == 0
    assert clean_plan["status"] == "NOTHING_TO_DISPATCH"
    for row in dirty_plan["lanes"]:
        assert row["difference_after_m"] == row["pending_m"] - row["assigned_m"]
    assert sum(row["responsibility_m"] for row in dirty_plan["lanes"]) == 5265


def test_broken_plan_refuses_to_publish(dirty_result, monkeypatch):
    original = dispatch_service.build_tasks

    def broken(batch, routes):
        tasks = original(batch, routes)
        return [task for task in tasks if task["responsibility_m"] != tasks[0]["responsibility_m"]] if len(tasks) > 1 else []

    monkeypatch.setattr(dispatch_service, "build_tasks", broken)
    with pytest.raises(DomainError) as caught:
        dispatch({"batch": "b", "at": "2026-01-17T06:16:00+08:00"}, dirty_result)
    assert caught.value.code in {"DISPATCH_UNBALANCED", "DISPATCH_DUPLICATE"}


# -- persistence / handover --------------------------------------------------

def start(client):
    response = client.post("/api/runs", json={"sample": "dirty"})
    assert response.status_code == 200, response.text
    return response.json()


def multi_task(run):
    return next(task for task in run["result"]["dispatch"]["tasks"] if len(task["stops"]) > 1)


def test_plan_is_published_with_the_run(client):
    run = start(client)
    assert run["dispatch"]["reused"] is False
    batch = run["manifest"]["batch"]
    view = client.get(f"/api/dispatch/plans/{batch}").json()
    assert [task["task_id"] for task in view["tasks"]] == [task["task_id"] for task in run["result"]["dispatch"]["tasks"]]
    assert view["summary"]["tasks"] == len(view["tasks"]) and view["summary"]["assigned_m"] == 1546
    assert all(task["status"] == "ASSIGNED" for task in view["tasks"])


def test_republishing_same_data_adds_no_tasks(client, dirty):
    first = start(client)
    second = client.post("/api/runs", json={"source": dirty}).json()
    assert second["dispatch"]["reused"] is True and second["dispatch"]["replaced"] is False
    batch = first["manifest"]["batch"]
    view = client.get(f"/api/dispatch/plans/{batch}").json()
    assert len(view["tasks"]) == len(first["result"]["dispatch"]["tasks"])
    assert len(view["events"]) == 0


def test_rerun_keeps_handover_and_list(client):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = multi_task(run)
    endpoint = f"/api/dispatch/plans/{batch}/handover"
    body = {"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁", "note": "早班领取"}
    accepted = client.post(endpoint, json=body).json()
    assert accepted["receipt"] == {"reused": False, "status": "ACCEPTED"}
    again = client.post(f"/api/runs/{run['id']}/rerun").json()
    assert again["dispatch"]["reused"] is True
    view = client.get(f"/api/dispatch/plans/{batch}").json()
    assert [item["task_id"] for item in view["tasks"]] == [item["task_id"] for item in accepted["tasks"]]
    assert view["summary"]["statuses"]["ACCEPTED"] == 1
    assert view["summary"]["accepted_m"] == task["responsibility_m"]


def test_handover_is_idempotent_and_audited(client):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = multi_task(run)
    endpoint = f"/api/dispatch/plans/{batch}/handover"
    body = {"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁", "note": ""}
    first = client.post(endpoint, json=body).json()
    second = client.post(endpoint, json=body).json()
    assert first["receipt"]["reused"] is False and second["receipt"]["reused"] is True
    assert len(second["events"]) == 1
    done = client.post(endpoint, json={**body, "status": "DONE"}).json()
    assert done["summary"]["statuses"]["DONE"] == 1
    assert done["summary"]["outstanding_m"] == 1546 - task["responsibility_m"]
    assert [event["status"] for event in done["events"]] == ["ACCEPTED", "DONE"]


def test_bad_transition_and_unknown_task(client):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = multi_task(run)
    endpoint = f"/api/dispatch/plans/{batch}/handover"
    body = {"task_id": task["task_id"], "status": "DONE", "actor": "周洁"}
    response = client.post(endpoint, json=body)
    assert response.status_code == 409 and response.json()["code"] == "BAD_TRANSITION"
    missing = client.post(endpoint, json={**body, "task_id": "nope", "status": "ACCEPTED"})
    assert missing.status_code == 404 and missing.json()["code"] == "TASK_NOT_FOUND"
    unnamed = client.post(endpoint, json={"task_id": task["task_id"], "status": "ACCEPTED"})
    assert unnamed.status_code == 422 and unnamed.json()["code"] == "ACTOR_REQUIRED"


def test_missing_plan_is_404(client):
    assert client.get("/api/dispatch/plans/不存在").status_code == 404


def test_failed_quantification_keeps_previous_list(client, dirty, monkeypatch):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = multi_task(run)
    endpoint = f"/api/dispatch/plans/{batch}/handover"
    client.post(endpoint, json={"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁"})
    before = client.get(f"/api/dispatch/plans/{batch}").json()

    original = dispatch_service.build_tasks
    monkeypatch.setattr(dispatch_service, "build_tasks", lambda batch, routes: [])
    failed = client.post("/api/runs", json={"source": {**dirty, "batch": "雪勤-0117-返工"}})
    assert failed.status_code == 409
    assert failed.json()["code"] == "DISPATCH_UNBALANCED"

    monkeypatch.setattr(dispatch_service, "build_tasks", original)
    after = client.get(f"/api/dispatch/plans/{batch}").json()
    assert after["tasks"] == before["tasks"] and after["summary"] == before["summary"]
    assert after["events"] == before["events"]


def test_new_plan_replaces_and_prunes_stale_handover(client, dirty):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = next(item for item in run["result"]["dispatch"]["tasks"]
                if any(stop["road"] == "S07" for stop in item["stops"]))
    client.post(f"/api/dispatch/plans/{batch}/handover",
                json={"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁"})
    # A new input for the same batch moves S07's responsibility out of the
    # gap, so the task carrying that stop no longer exists.
    changed = {**dirty, "roads": [
        {**row, "from_m": 0, "to_m": 200} if row["road"] == "S07" else row
        for row in dirty["roads"]]}
    updated = client.post("/api/runs", json={"source": changed}).json()
    assert updated["dispatch"]["reused"] is False
    assert updated["dispatch"]["replaced"] is True
    view = client.get(f"/api/dispatch/plans/{batch}").json()
    assert task["task_id"] not in [item["task_id"] for item in view["tasks"]]
    assert view["summary"]["statuses"]["ACCEPTED"] == 0
    assert view["summary"]["assigned_m"] == view["totals"]["pending_m"]
    assert view["totals"]["pending_m"] == 1546 - 125
    assert all(stop["road"] != "S07" for item in view["tasks"] for stop in item["stops"])


def test_unchanged_tasks_keep_handover_when_plan_is_replaced(client, dirty):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = next(item for item in run["result"]["dispatch"]["tasks"]
                if all(stop["road"] != "S07" for stop in item["stops"]))
    client.post(f"/api/dispatch/plans/{batch}/handover",
                json={"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁"})
    changed = {**dirty, "roads": [
        {**row, "from_m": 0, "to_m": 200} if row["road"] == "S07" else row
        for row in dirty["roads"]]}
    client.post("/api/runs", json={"source": changed})
    view = client.get(f"/api/dispatch/plans/{batch}").json()
    kept = next(item for item in view["tasks"] if item["task_id"] == task["task_id"])
    assert kept["status"] == "ACCEPTED"


def test_store_failure_rolls_back_run_and_keeps_plan(client, dirty, monkeypatch):
    run = start(client)
    batch = run["manifest"]["batch"]
    task = multi_task(run)
    client.post(f"/api/dispatch/plans/{batch}/handover",
                json={"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁"})
    before = client.get(f"/api/dispatch/plans/{batch}").json()
    runs_before = client.get("/api/runs").json()["runs"]

    from app.store import Ledger
    original = Ledger._publish

    def explode(self, *args, **kwargs):
        raise DomainError("STORAGE_FAILED", "存储不可用", 500)

    monkeypatch.setattr(Ledger, "_publish", explode)
    failed = client.post("/api/runs", json={"source": {**dirty, "batch": "雪勤-0117-返工"}})
    assert failed.status_code == 500
    monkeypatch.setattr(Ledger, "_publish", original)

    assert client.get(f"/api/dispatch/plans/{batch}").json() == before
    assert client.get("/api/runs").json()["runs"] == runs_before
    assert client.get("/api/dispatch/plans/雪勤-0117-返工").status_code == 404


def test_resume_publishes_without_touching_run(client):
    run = start(client)
    batch = run["manifest"]["batch"]
    before = client.get(f"/api/runs/{run['id']}").json()
    resumed = client.post(f"/api/runs/{run['id']}/dispatch").json()
    assert resumed["dispatch"]["reused"] is True
    assert client.get(f"/api/runs/{run['id']}").json() == before


def test_plan_survives_reopen(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    with TestClient(create_app(path)) as client:
        run = start(client)
        batch = run["manifest"]["batch"]
        task = multi_task(run)
        client.post(f"/api/dispatch/plans/{batch}/handover",
                    json={"task_id": task["task_id"], "status": "ACCEPTED", "actor": "周洁"})
        frozen = client.get(f"/api/dispatch/plans/{batch}").json()
    with TestClient(create_app(path)) as reopened:
        assert reopened.get(f"/api/dispatch/plans/{batch}").json() == frozen


def test_dispatch_preview_endpoint(client):
    response = client.get("/api/dispatch/dirty")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["assigned_m"] == body["totals"]["pending_m"]
    assert body["status"] == "READY"
