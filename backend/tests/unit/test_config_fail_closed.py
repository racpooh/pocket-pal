"""Real provider requested + incomplete config must fail, never fall back to a mock."""

import pytest

from finassist.providers import BudgetExceeded, FakeExtractionProvider, UsageMeter
from finassist.settings import ConfigError, Settings


def _s(**kw):
    return Settings(_env_file=None, **kw)


def test_anthropic_without_key_fails():
    with pytest.raises(ConfigError):
        _s(model_provider="anthropic", model_api_key=None).require_real_provider()
    with pytest.raises(ConfigError):
        _s(model_provider="anthropic", model_api_key="   ").require_real_provider()


def test_unknown_provider_fails():
    with pytest.raises(ConfigError):
        _s(model_provider="openai").require_real_provider()


def test_worker_and_app_do_not_fall_back(monkeypatch):
    from finassist.api.app import build_chat_model
    from finassist.worker import build_provider

    for fn in (build_provider, build_chat_model):
        with pytest.raises(ConfigError):
            fn(_s(model_provider="anthropic", model_api_key=None))
    assert isinstance(build_provider(_s(model_provider="fake")), FakeExtractionProvider)
    assert build_chat_model(_s(model_provider="fake")) is None  # → /chat returns 503, not a fake answer


def test_describe_never_contains_key():
    d = _s(model_provider="anthropic", model_api_key="sk-ant-secret-value").describe()
    assert d["api_key_present"] is True and "sk-ant-secret-value" not in repr(d)


def test_meter_blocks_before_overspend(tmp_path):
    m = UsageMeter(budget_usd=0.001, max_requests=10, ledger_path=str(tmp_path / "l.jsonl"))
    m.check("claude-haiku-5-5", 2_000, 400)  # worst case 0.0002 + 0.0002 = 0.0004 ≤ 0.001
    m.record("claude-haiku-5-5", 2_000, 400, "test")
    with pytest.raises(BudgetExceeded):
        m.check("claude-sonnet-5-5", 2_000, 700)  # 0.004 + 0.007 > remaining
    m2 = UsageMeter(budget_usd=1.0, max_requests=1)
    m2.record("claude-haiku-5-5", 1, 1, "x")
    with pytest.raises(BudgetExceeded):
        m2.check("claude-haiku-5-5", 1, 1)
    assert UsageMeter(budget_usd=0.001, max_requests=10, ledger_path=str(tmp_path / "l.jsonl")).prior_cost_usd > 0  # persisted


def test_meter_refuses_unpriced_model():
    with pytest.raises(BudgetExceeded):
        UsageMeter(budget_usd=1, max_requests=1).check("some-new-model", 1, 1)


def test_provider_must_be_explicit_and_fake_only_in_dev_test():
    """CP3a: no silent fake. Unset provider fails; fake is refused in sandbox/production."""
    with pytest.raises(ConfigError):
        _s().require_real_provider()
    for env in ("sandbox", "production"):
        with pytest.raises(ConfigError):
            _s(model_provider="fake", env=env).require_real_provider()
    for env in ("dev", "test"):
        _s(model_provider="fake", env=env).require_real_provider()


def test_health_reports_test_mode():
    from fastapi.testclient import TestClient

    from finassist.api.app import create_app

    h = TestClient(create_app(_s(model_provider="fake", env="test"))).get("/v1/health").json()
    assert h["test_mode"] is True and h["env"] == "test"
