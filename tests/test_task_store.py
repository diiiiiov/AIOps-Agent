from types import SimpleNamespace

from app.services.task_store import TaskStore


def test_task_and_idempotency_key_are_persisted(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.db"))
    record = SimpleNamespace(
        task_id="task-1", session_id="session-1", tenant_id="tenant-a",
        idempotency_key="incident-1", context=None, status="queued", attempts=0,
        events=[], error=None, created_at=1.0, updated_at=1.0,
    )
    store.upsert(record)
    rows = store.load_all()
    assert rows[0]["tenant_id"] == "tenant-a"
    assert rows[0]["idempotency_key"] == "incident-1"


def test_interrupted_tasks_are_marked_failed(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.db"))
    record = SimpleNamespace(
        task_id="task-1", session_id="session-1", tenant_id="tenant-a",
        idempotency_key=None, context=None, status="running", attempts=1,
        events=[], error=None, created_at=1.0, updated_at=1.0,
    )
    store.upsert(record)
    store.recover_interrupted()
    assert store.load_all()[0]["status"] == "failed"
