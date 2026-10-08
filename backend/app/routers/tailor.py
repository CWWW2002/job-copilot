from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.models import JobDescription, Resume, TailoredResume
from app.services.tailor_service import TailorGenerationError, generate_tailored_resume

router = APIRouter(prefix="/api/tailor", tags=["tailor"])


class TailorCreateRequest(BaseModel):
    resume_id: int
    jd_id: int
    market_style: Literal["us", "china"]


def _serialize(tailored: TailoredResume) -> dict:
    return {
        "id": tailored.id,
        "resume_id": tailored.resume_id,
        "jd_id": tailored.jd_id,
        "market_style": tailored.market_style,
        "content": tailored.content,
    }


@router.post("")
def create_tailored_resume(payload: TailorCreateRequest, session: Session = Depends(get_session)):
    resume = session.get(Resume, payload.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    jd = session.get(JobDescription, payload.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="JD不存在")

    try:
        content = generate_tailored_resume(resume.content_text, jd.raw_text, payload.market_style)
    except TailorGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    tailored = TailoredResume(
        resume_id=resume.id,
        jd_id=jd.id,
        market_style=payload.market_style,
        content=content,
    )
    session.add(tailored)
    session.commit()
    session.refresh(tailored)

    return _serialize(tailored)


@router.get("/{tailored_id}")
def get_tailored_resume(tailored_id: int, session: Session = Depends(get_session)):
    tailored = session.get(TailoredResume, tailored_id)
    if not tailored:
        raise HTTPException(status_code=404, detail="定制简历不存在")
    return _serialize(tailored)
