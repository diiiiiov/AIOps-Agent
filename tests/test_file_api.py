from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import file as file_api


def test_index_directory_uses_tenant_upload_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(file_api, "UPLOAD_DIR", tmp_path)
    captured = {}

    def fake_index_directory(path, *, tenant_id):
        captured.update(path=path, tenant_id=tenant_id)
        return SimpleNamespace(success=True, to_dict=lambda: {"indexed": 2})

    monkeypatch.setattr(
        file_api.vector_index_service,
        "index_directory",
        fake_index_directory,
    )
    app = FastAPI()
    app.include_router(file_api.router, prefix="/api")

    response = TestClient(app).post("/api/index_directory")

    assert response.status_code == 200
    assert response.json()["data"] == {"indexed": 2}
    assert captured == {
        "path": str(tmp_path / "public"),
        "tenant_id": "public",
    }
