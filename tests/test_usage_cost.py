from app.config import config
from app.core.usage_tracker import calculate_cost


def test_calculates_input_and_output_cost(monkeypatch):
    monkeypatch.setattr(config, "llm_pricing_json", '{"m":{"input":1.0,"output":2.0}}')
    assert calculate_cost("m", 1_000_000, 500_000) == 2.0


def test_unknown_model_has_zero_cost(monkeypatch):
    monkeypatch.setattr(config, "llm_pricing_json", "{}")
    assert calculate_cost("unknown", 1000, 1000) == 0
