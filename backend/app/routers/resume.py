from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session

from app.database import get_session
from app.models import Resume
from app.services.parser import (
    EmptyResumeTextError,
    UnsupportedFileTypeError,
    parse_resume,
)

router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_resume(file: UploadFile, session: Session = Depends(get_session)):
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="文件过大,请上传小于10MB的文件")

    try:
        file_type, text = parse_resume(file.filename or "", file_bytes)
    except UnsupportedFileTypeError:
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 DOCX 格式")
    except EmptyResumeTextError as e:
        raise HTTPException(status_code=422, detail=str(e))

    resume = Resume(filename=file.filename or "resume", file_type=file_type, content_text=text)
    session.add(resume)
    session.commit()
    session.refresh(resume)

    return {
        "id": resume.id,
        "filename": resume.filename,
        "file_type": resume.file_type,
        "content_text": resume.content_text,
        "char_count": len(resume.content_text),
    }


@router.get("/{resume_id}")
def get_resume(resume_id: int, session: Session = Depends(get_session)):
    resume = session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    return resume
