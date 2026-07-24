# Integration test environment

The disposable integration stack covers PostgreSQL, Milvus and both MCP servers.
It uses test-only loopback ports and temporary container filesystems, so it does
not reuse development or production data.

## Run

From PowerShell:

```powershell
.\scripts\integration-test.ps1
```

The script starts PostgreSQL (`55432`), Milvus (`19531`) and its dependencies,
then starts the CLS and monitor MCP servers on `18003` and `18004`. It waits for
all services, runs `tests/test_integration_stack.py`, and removes containers and
processes in a `finally` block.

Use `-KeepRunning` when debugging the database containers. The MCP child
processes are always stopped to prevent stale test servers.

## Optional all-container MCP mode

For CI hosts that can access Docker Hub, enable the optional MCP profile:

```powershell
docker compose -f docker-compose.integration.yml --profile container-mcp up -d --build --wait
```

The default path intentionally runs MCP from `.runtime-venv`, which makes local
tests independent of Docker Hub availability while exercising the same server
code and HTTP protocol.
