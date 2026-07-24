import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException

from app.config import config
from app.security import verify_bearer_token


def _part(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def _token(payload: dict, secret: str) -> str:
    header, body = _part({"alg": "HS256", "typ": "JWT"}), _part(payload)
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{body}.{signature}"


def test_valid_token(monkeypatch):
    monkeypatch.setattr(config, "auth_secret", "test-secret")
    monkeypatch.setattr(config, "auth_issuer", "issuer")
    token = _token({"sub": "u1", "tenant_id": "t1", "roles": ["operator"],
                    "iss": "issuer", "exp": time.time() + 60}, "test-secret")
    claims = verify_bearer_token(f"Bearer {token}")
    assert claims["tenant_id"] == "t1"


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "auth_secret", "test-secret")
    token = _token({"sub": "u1", "tenant_id": "t1", "exp": time.time() - 1}, "test-secret")
    with pytest.raises(HTTPException) as exc:
        verify_bearer_token(f"Bearer {token}")
    assert exc.value.status_code == 401
