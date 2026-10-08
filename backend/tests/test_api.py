from fastapi.testclient import TestClient
from sqlmodel import Session

from app.database import engine
from app.main import app
from app.models import LLMCall

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_usage_aggregates_by_task_and_model():
    with Session(engine) as session:
        session.add(LLMCall(task="tailor", route="main", model="m1", input_tokens=100, output_tokens=50, cost_usd=0.01))
        session.add(LLMCall(task="tailor", route="main", model="m1", input_tokens=100, output_tokens=50, cost_usd=0.02))
        session.add(LLMCall(task="market_detect", route="light", model="m2", cost_usd=0.001))
        session.add(LLMCall(task="match", route="main", model="", success=False, error="boom"))
        session.commit()

    usage = client.get("/api/usage").json()

    assert usage["total_calls"] == 4
    assert usage["failed_calls"] == 1
    assert usage["total_cost_usd"] == 0.031
    tailor = next(t for t in usage["by_task"] if t["name"] == "tailor")
    assert tailor == {"name": "tailor", "calls": 2, "input_tokens": 200, "output_tokens": 100, "cost_usd": 0.03}
    # 失败的调用不计入分组统计
    assert {t["name"] for t in usage["by_task"]} == {"tailor", "market_detect"}


def test_jd_with_clear_keywords_skips_llm():
    """关键词能判断的 JD 不调用 LLM(规则优先)。"""
    jd = "岗位职责:负责后端开发。任职要求:本科及以上,应届生校招,五险一金,工作地点深圳。"

    body = client.post("/api/jd", json={"raw_text": jd}).json()

    assert body["suggested_market_style"] == "china"
    assert body["suggestion_method"] == "keyword"


def test_jd_too_short_is_rejected():
    assert client.post("/api/jd", json={"raw_text": "太短"}).status_code == 422
