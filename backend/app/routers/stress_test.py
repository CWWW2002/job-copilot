import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlmodel import Session

from app.database import get_session
from app.models import JobDescription, Resume, StressTestResult, TailoredResume
from app.services.stress_test_service import StressTestParseError, generate_stress_test

router = APIRouter(prefix="/api/resume", tags=["stress-test"])


class StressTestCreateRequest(BaseModel):
    resume_source: Literal["original", "tailored"]
    resume_id: Optional[int] = None
    tailored_resume_id: Optional[int] = None

    @model_validator(mode="after")
    def check_id_matches_source(self):
        if self.resume_source == "original" and not self.resume_id:
            raise ValueError("resume_source为'original'时必须提供resume_id")
        if self.resume_source == "tailored" and not self.tailored_resume_id:
            raise ValueError("resume_source为'tailored'时必须提供tailored_resume_id")
        return self


def _serialize(result: StressTestResult) -> dict:
    return {
        "id": result.id,
        "resume_source": result.resume_source,
        "resume_id": result.resume_id,
        "tailored_resume_id": result.tailored_resume_id,
        "jd_id": result.jd_id,
        "groups": json.loads(result.result_json),
    }


@router.post("/stress-test")
def create_stress_test(payload: StressTestCreateRequest, session: Session = Depends(get_session)):
    jd_id = None
    jd_text = None

    if payload.resume_source == "original":
        resume = session.get(Resume, payload.resume_id)
        if not resume:
            raise HTTPException(status_code=404, detail="简历不存在")
        resume_text = resume.content_text
        resume_id = resume.id
        tailored_resume_id = None
    else:
        tailored = session.get(TailoredResume, payload.tailored_resume_id)
        if not tailored:
            raise HTTPException(status_code=404, detail="定制简历不存在")
        resume_text = tailored.content
        resume_id = None
        tailored_resume_id = tailored.id
        jd_id = tailored.jd_id
        jd = session.get(JobDescription, jd_id)
        jd_text = jd.raw_text if jd else None

    try:
        groups = generate_stress_test(resume_text, jd_text)
    except StressTestParseError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = StressTestResult(
        resume_source=payload.resume_source,
        resume_id=resume_id,
        tailored_resume_id=tailored_resume_id,
        jd_id=jd_id,
        result_json=json.dumps(groups, ensure_ascii=False),
    )
    session.add(result)
    session.commit()
    session.refresh(result)

    return _serialize(result)


@router.get("/stress-test/{result_id}")
def get_stress_test(result_id: int, session: Session = Depends(get_session)):
    result = session.get(StressTestResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="压力测试结果不存在")
    return _serialize(result)
