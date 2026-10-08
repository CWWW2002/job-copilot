import functools

import pytest
from sqlmodel import Session, select

from app.database import engine
from app.models import LLMCall
from app.services import llm_client


@pytest.fixture
def mock_router(monkeypatch):
    """把 Router.completion 替换为带 mock 参数的版本,不发出真实请求。"""
    router = llm_client.get_router()
    original = router.completion

    def use(**mock_kwargs):
        monkeypatch.setattr(router, "completion", functools.partial(original, **mock_kwargs))

    return use


def _calls() -> list[LLMCall]:
    with Session(engine) as session:
        return session.exec(select(LLMCall)).all()


def test_classification_task_routes_to_light_model(mock_router):
    mock_router(mock_response='{"market_style": "us"}')

    assert llm_client.complete("market_detect", "x", max_tokens=1024) == '{"market_style": "us"}'

    [call] = _calls()
    assert call.route == "light"
    assert call.model == llm_client.LIGHT_MODEL
    assert call.success and call.cost_usd > 0


def test_generation_task_routes_to_main_model(mock_router):
    mock_router(mock_response="定制简历")

    llm_client.complete("tailor", "x", max_tokens=3000)

    [call] = _calls()
    assert call.route == "main"
    assert call.model == llm_client.MODEL_NAME


def test_main_model_failure_falls_back(mock_router):
    mock_router(mock_response="兜底结果", mock_testing_fallbacks=True)

    assert llm_client.complete("match", "x", max_tokens=2000) == "兜底结果"

    [call] = _calls()
    assert call.route == "main"
    assert call.model == llm_client.FALLBACK_MODEL


def test_total_failure_is_logged_and_raised(mock_router):
    mock_router(mock_response=Exception("boom"))

    with pytest.raises(RuntimeError, match="LLM 调用失败"):
        llm_client.complete("stress_test", "x", max_tokens=4000)

    [call] = _calls()
    assert not call.success
    assert call.error


def test_unknown_task_is_rejected():
    with pytest.raises(KeyError):
        llm_client.complete("not_a_task", "x", max_tokens=10)


def test_light_model_is_much_cheaper_than_main(mock_router):
    """分类任务路由到轻量模型的意义:同样的 token 数,成本应显著低于主力模型。"""
    mock_router(mock_response="x")
    llm_client.complete("market_detect", "x", max_tokens=1024)
    llm_client.complete("tailor", "x", max_tokens=1024)

    light, main = sorted(_calls(), key=lambda c: c.cost_usd)
    assert light.route == "light" and main.route == "main"
    assert light.cost_usd < main.cost_usd * 0.1
