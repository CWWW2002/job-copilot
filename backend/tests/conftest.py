import os
import tempfile
from pathlib import Path

# 必须在导入 app 之前设置:测试使用临时数据库,且不需要真实的 API key(所有 LLM 调用都会被 mock)
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

from app.database import create_db_and_tables, engine  # noqa: E402
from app.models import LLMCall  # noqa: E402

create_db_and_tables()


@pytest.fixture(autouse=True)
def clean_llm_calls():
    with Session(engine) as session:
        session.exec(delete(LLMCall))
        session.commit()
    yield
