from langchain_core.documents import Document

from app.core.request_context import RequestContext
from app.tools.knowledge_tool import _can_read


def test_private_document_only_visible_to_owner():
    document = Document(page_content="secret", metadata={
        "_tenant_id": "t1", "_visibility": "private", "_owner_id": "u1"
    })
    assert _can_read(document, RequestContext(tenant_id="t1", user_id="u1"))
    assert not _can_read(document, RequestContext(tenant_id="t1", user_id="u2"))


def test_restricted_document_requires_role_and_tenant():
    document = Document(page_content="runbook", metadata={
        "_tenant_id": "t1", "_visibility": "restricted", "_allowed_roles": ["sre"]
    })
    assert _can_read(document, RequestContext(tenant_id="t1", user_id="u1", roles=("sre",)))
    assert not _can_read(document, RequestContext(tenant_id="t2", user_id="u1", roles=("sre",)))
