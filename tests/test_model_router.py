import pytest

from app.core.model_router import ModelRouter


def test_rejects_unapproved_model_endpoint():
    router = ModelRouter()
    with pytest.raises(ValueError):
        router.switch(model="example", base_url="https://attacker.example/v1")


def test_rejects_non_https_model_endpoint():
    router = ModelRouter()
    with pytest.raises(ValueError):
        router.switch(model="example", base_url="http://localhost:8000/v1")
