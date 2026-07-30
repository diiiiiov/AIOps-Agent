"""Black-box checks for the disposable PostgreSQL, Milvus and MCP stack."""

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="set RUN_INTEGRATION=1 and start docker-compose.integration.yml",
    ),
]


def test_postgres_task_store_claims_a_task():
    from app.services.postgres_task_store import PostgresTaskStore

    dsn = os.getenv(
        "INTEGRATION_POSTGRES_DSN",
        "postgresql://test:test@127.0.0.1:55432/ops_diagnosis_test",
    )
    store = PostgresTaskStore(dsn)
    task_id = f"integration-{uuid4().hex}"
    record = SimpleNamespace(
        task_id=task_id,
        session_id="integration",
        tenant_id="integration",
        idempotency_key=task_id,
        context=None,
        status="queued",
        attempts=0,
        events=[],
        error=None,
        created_at=1.0,
        updated_at=1.0,
    )
    store.upsert(record)
    claimed = store.claim_next()
    assert claimed is not None
    assert claimed["task_id"] == task_id
    assert claimed["status"] == "running"


def test_milvus_accepts_client_connections():
    from pymilvus import MilvusClient

    uri = os.getenv("INTEGRATION_MILVUS_URI", "http://127.0.0.1:19531")
    client = MilvusClient(uri=uri)
    assert isinstance(client.list_collections(), list)
    client.close()


@pytest.mark.asyncio
async def test_mcp_servers_publish_expected_tools():
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "cls": {
                "transport": "streamable_http",
                "url": os.getenv("INTEGRATION_MCP_CLS_URL", "http://127.0.0.1:18003/mcp"),
            },
            "monitor": {
                "transport": "streamable_http",
                "url": os.getenv(
                    "INTEGRATION_MCP_MONITOR_URL", "http://127.0.0.1:18004/mcp"
                ),
            },
        }
    )
    names = {tool.name for tool in await client.get_tools()}
    assert "get_current_timestamp" in names
    assert "query_cpu_metrics" in names
