"""统一的 LLM 调用层:基于 LiteLLM Router 实现多模型接入、按任务路由、失败兜底和 token 成本追踪。

各业务模块只需调用 complete(task, prompt, max_tokens),不关心具体用哪个模型。
每次调用(含失败)都会写入 LLMCall 表,可通过 /api/usage 查看成本统计。
"""

import logging
import os
import time
from functools import lru_cache

import litellm
from anthropic import Anthropic
from litellm import Router
from sqlmodel import Session

from app.database import engine
from app.models import LLMCall

logger = logging.getLogger(__name__)


def _with_provider(model: str) -> str:
    """LiteLLM 需要 provider 前缀;环境变量里只写模型名时默认是 Anthropic。"""
    return model if "/" in model else f"anthropic/{model}"


# 主力模型:负责匹配分析、简历定制、压力测试等生成类任务
MODEL_NAME = os.getenv("LLM_MAIN_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
# 轻量模型:负责 JD 市场风格判断这类简单分类任务,成本约为主力模型的几十分之一
LIGHT_MODEL = os.getenv("LLM_LIGHT_MODEL", "claude-haiku-5-5")
# 兜底模型:主力模型调用失败(限流、服务异常等)时自动切换
FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "claude-sonnet-5-5")

# 任务 -> 路由组
TASK_ROUTES = {
    "market_detect": "light",
    "match": "main",
    "tailor": "main",
    "stress_test": "main",
    "eval_generate": "main",  # 幻觉率测试中的生成,与线上 tailor 走同一路由
}


@lru_cache
def get_router() -> Router:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY 未设置,请在 backend/.env 中配置")
    return Router(
        model_list=[
            {"model_name": "main", "litellm_params": {"model": _with_provider(MODEL_NAME)}},
            {"model_name": "light", "litellm_params": {"model": _with_provider(LIGHT_MODEL)}},
            {"model_name": "fallback", "litellm_params": {"model": _with_provider(FALLBACK_MODEL)}},
        ],
        # 轻量模型失败时退回主力模型,主力模型失败时退回兜底模型
        fallbacks=[{"light": ["main"]}, {"main": ["fallback"]}],
        num_retries=2,
    )


def _log_call(**fields) -> None:
    # 记录失败不能影响业务请求
    try:
        with Session(engine) as session:
            session.add(LLMCall(**fields))
            session.commit()
    except Exception:
        logger.exception("记录 LLM 调用失败")


def complete(task: str, prompt: str, max_tokens: int) -> str:
    route = TASK_ROUTES[task]
    started = time.monotonic()
    try:
        response = get_router().completion(
            model=route,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        _log_call(
            task=task,
            route=route,
            model="",
            latency_ms=int((time.monotonic() - started) * 1000),
            success=False,
            error=f"{type(e).__name__}: {e}"[:500],
        )
        raise RuntimeError(f"LLM 调用失败: {e}") from e

    cost = response._hidden_params.get("response_cost")
    if cost is None:
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            cost = 0.0
    _log_call(
        task=task,
        route=route,
        model=response.model or "",
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
        cost_usd=cost,
        latency_ms=int((time.monotonic() - started) * 1000),
        success=True,
    )
    return response.choices[0].message.content or ""


@lru_cache
def get_client() -> Anthropic:
    """直连 Anthropic SDK 的客户端。业务代码请用 complete();这里仅供幻觉率测试的评审模型使用。"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 未设置,请在 backend/.env 中配置")
    return Anthropic(api_key=api_key)
