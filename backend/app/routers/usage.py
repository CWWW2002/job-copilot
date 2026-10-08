from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import LLMCall

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _group_by(session: Session, column) -> list[dict]:
    rows = session.exec(
        select(
            column,
            func.count(LLMCall.id),
            func.sum(LLMCall.input_tokens),
            func.sum(LLMCall.output_tokens),
            func.sum(LLMCall.cost_usd),
        )
        .where(LLMCall.success)
        .group_by(column)
        .order_by(func.sum(LLMCall.cost_usd).desc())
    ).all()
    return [
        {
            "name": name,
            "calls": calls,
            "input_tokens": input_tokens or 0,
            "output_tokens": output_tokens or 0,
            "cost_usd": round(cost or 0.0, 6),
        }
        for name, calls, input_tokens, output_tokens, cost in rows
    ]


@router.get("")
def get_usage(session: Session = Depends(get_session)):
    """LLM 调用成本统计:总计、按任务、按实际模型,以及最近 20 次调用。"""
    total_calls = session.exec(select(func.count(LLMCall.id))).one()
    failed_calls = session.exec(select(func.count(LLMCall.id)).where(LLMCall.success == False)).one()  # noqa: E712
    total_cost = session.exec(select(func.sum(LLMCall.cost_usd))).one() or 0.0
    recent = session.exec(select(LLMCall).order_by(LLMCall.id.desc()).limit(20)).all()

    return {
        "total_calls": total_calls,
        "failed_calls": failed_calls,
        "total_cost_usd": round(total_cost, 6),
        "by_task": _group_by(session, LLMCall.task),
        "by_model": _group_by(session, LLMCall.model),
        "recent": recent,
    }
