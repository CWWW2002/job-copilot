import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.models import JobDescription, MatchReport, Resume
from app.services.match_service import MatchReportParseError, generate_match_report

router = APIRouter(prefix="/api/match", tags=["match"])


class MatchCreateRequest(BaseModel):
    resume_id: int
    jd_id: int
    market_style: Literal["us", "china"]


def _serialize(match_report: MatchReport) -> dict:
    return {
        "id": match_report.id,
        "resume_id": match_report.resume_id,
        "jd_id": match_report.jd_id,
        "market_style": match_report.market_style,
        "score": match_report.score,
        "matched_skills": json.loads(match_report.matched_skills_json),
        "missing_skills": json.loads(match_report.missing_skills_json),
        "summary": {"zh": match_report.summary_zh, "en": match_report.summary_en},
    }


@router.post("")
def create_match(payload: MatchCreateRequest, session: Session = Depends(get_session)):
    resume = session.get(Resume, payload.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    jd = session.get(JobDescription, payload.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="JD不存在")

    try:
        result = generate_match_report(resume.content_text, jd.raw_text, payload.market_style)
    except MatchReportParseError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    match_report = MatchReport(
        resume_id=resume.id,
        jd_id=jd.id,
        market_style=payload.market_style,
        score=result["score"],
        matched_skills_json=json.dumps(result["matched_skills"], ensure_ascii=False),
        missing_skills_json=json.dumps(result["missing_skills"], ensure_ascii=False),
        summary_zh=result["summary_zh"],
        summary_en=result["summary_en"],
    )
    session.add(match_report)
    session.commit()
    session.refresh(match_report)

    return _serialize(match_report)


@router.get("/{match_id}")
def get_match(match_id: int, session: Session = Depends(get_session)):
    match_report = session.get(MatchReport, match_id)
    if not match_report:
        raise HTTPException(status_code=404, detail="匹配报告不存在")
    return _serialize(match_report)
