from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.models import JobDescription
from app.services.market_detector import detect_market_style

router = APIRouter(prefix="/api/jd", tags=["jd"])


class JDCreateRequest(BaseModel):
    raw_text: str


@router.post("")
def create_jd(payload: JDCreateRequest, session: Session = Depends(get_session)):
    text = payload.raw_text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="JD文本不能为空")
    if len(text) < 20:
        raise HTTPException(status_code=422, detail="JD文本过短,请粘贴完整的职位描述")

    suggested_market_style, suggestion_method = detect_market_style(text)

    jd = JobDescription(
        raw_text=text,
        suggested_market_style=suggested_market_style,
        suggestion_method=suggestion_method,
    )
    session.add(jd)
    session.commit()
    session.refresh(jd)

    return {
        "id": jd.id,
        "suggested_market_style": jd.suggested_market_style,
        "suggestion_method": jd.suggestion_method,
        "char_count": len(text),
    }


@router.get("/{jd_id}")
def get_jd(jd_id: int, session: Session = Depends(get_session)):
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="JD不存在")
    return jd
