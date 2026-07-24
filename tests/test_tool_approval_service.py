from app.config import config
from app.services.tool_approval_service import ToolApprovalService


def test_approval_token_is_single_use_and_bound_to_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "task_store_path", str(tmp_path / "tasks.db"))
    service = ToolApprovalService()
    approval_id = service.create(
        tenant_id="tenant-a", user_id="u1", tool_name="restart_service",
        args={"service": "payment"},
    )
    token = service.approve(approval_id, tenant_id="tenant-a", approver="admin")
    assert token
    assert not service.consume(
        approval_id=approval_id, token=token, tenant_id="tenant-a",
        tool_name="restart_service", args={"service": "other"},
    )
    assert service.consume(
        approval_id=approval_id, token=token, tenant_id="tenant-a",
        tool_name="restart_service", args={"service": "payment"},
    )
    assert not service.consume(
        approval_id=approval_id, token=token, tenant_id="tenant-a",
        tool_name="restart_service", args={"service": "payment"},
    )
