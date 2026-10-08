import os
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

# 容器部署时通过 DATABASE_PATH 指向挂载卷,保证重建容器后数据不丢失
DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent.parent / "app.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    import app.models  # noqa: F401  确保所有表(含 LLMCall)都已注册到 metadata

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
