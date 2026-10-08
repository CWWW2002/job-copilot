from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables
from app.routers import jd, match, resume, stress_test, tailor, usage

app = FastAPI(title="求职简历投递辅助工具 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(resume.router)
app.include_router(jd.router)
app.include_router(match.router)
app.include_router(tailor.router)
app.include_router(stress_test.router)
app.include_router(usage.router)
