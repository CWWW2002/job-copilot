from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Resume(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    file_type: str  # "pdf" | "docx"
    content_text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobDescription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    raw_text: str
    suggested_market_style: str  # "us" | "china" — default suggestion only, not final
    suggestion_method: str  # "keyword" | "llm"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    resume_id: int = Field(foreign_key="resume.id")
    jd_id: int = Field(foreign_key="jobdescription.id")
    market_style: str  # "us" | "china" — explicitly chosen by the user
    score: int
    matched_skills_json: str
    missing_skills_json: str
    summary_zh: str
    summary_en: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TailoredResume(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    resume_id: int = Field(foreign_key="resume.id")
    jd_id: int = Field(foreign_key="jobdescription.id")
    market_style: str  # "us" | "china" — explicitly chosen by the user
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StressTestResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    resume_source: str  # "original" | "tailored"
    resume_id: Optional[int] = Field(default=None, foreign_key="resume.id")
    tailored_resume_id: Optional[int] = Field(default=None, foreign_key="tailoredresume.id")
    jd_id: Optional[int] = Field(default=None, foreign_key="jobdescription.id")
    result_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LLMCall(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task: str  # "match" | "tailor" | "stress_test" | "market_detect" | ...
    route: str  # LiteLLM 路由组:"main" | "light"
    model: str  # 实际响应的模型(发生兜底时与路由组的默认模型不同)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
