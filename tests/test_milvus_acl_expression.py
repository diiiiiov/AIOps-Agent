from app.core.request_context import RequestContext
from app.tools.knowledge_tool import build_acl_expr


def test_expression_contains_tenant_owner_and_roles():
    expression = build_acl_expr(RequestContext(
        tenant_id="tenant-a", user_id="user-1", roles=("operator", "sre")
    ))
    assert 'metadata["_tenant_id"] == "tenant-a"' in expression
    assert 'metadata["_owner_id"] == "user-1"' in expression
    assert 'json_contains(metadata["_allowed_roles"], "operator")' in expression


def test_admin_expression_is_still_tenant_scoped():
    expression = build_acl_expr(RequestContext(
        tenant_id="tenant-a", user_id="admin-1", roles=("admin",)
    ))
    assert expression == 'metadata["_tenant_id"] == "tenant-a"'


def test_expression_values_are_escaped():
    expression = build_acl_expr(RequestContext(
        tenant_id='tenant" or true', user_id="u1", roles=()
    ))
    assert '\\"' in expression
