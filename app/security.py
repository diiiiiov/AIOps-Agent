"""轻量 JWT 验证与 RBAC 辅助。

生产环境建议将密钥验证替换为 OIDC JWKS；HS256 实现用于单体部署和本地网关过渡。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException

from app.config import config


def _decode_part(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_bearer_token(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer 认证令牌")
    token = authorization[7:].strip()
    parts = token.split(".")
    if len(parts) != 3 or not config.auth_secret:
        raise HTTPException(status_code=401, detail="认证令牌格式无效")
    encoded_header, encoded_payload, signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    expected = base64.urlsafe_b64encode(
        hmac.new(config.auth_secret.encode(), signing_input, hashlib.sha256).digest()
    ).decode().rstrip("=")
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="认证令牌签名无效")
    try:
        header = json.loads(_decode_part(encoded_header))
        claims = json.loads(_decode_part(encoded_payload))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="认证令牌内容无效") from exc
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="不支持的令牌算法")
    if claims.get("exp") is not None and float(claims["exp"]) <= time.time():
        raise HTTPException(status_code=401, detail="认证令牌已过期")
    if config.auth_issuer and claims.get("iss") != config.auth_issuer:
        raise HTTPException(status_code=401, detail="认证令牌签发方无效")
    if not claims.get("sub") or not claims.get("tenant_id"):
        raise HTTPException(status_code=401, detail="令牌缺少 sub 或 tenant_id")
    roles = claims.get("roles", [])
    claims["roles"] = [roles] if isinstance(roles, str) else roles
    return claims


def has_role(claims: dict[str, Any], required: str) -> bool:
    roles = set(claims.get("roles", []))
    if required in roles or "admin" in roles:
        return True
    if required == "viewer" and roles.intersection({"operator", "knowledge_admin"}):
        return True
    return False
