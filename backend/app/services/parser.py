import io

from docx import Document
from pypdf import PdfReader


class UnsupportedFileTypeError(Exception):
    pass


class EmptyResumeTextError(Exception):
    pass


def parse_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


def parse_docx(file_bytes: bytes) -> str:
    document = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in document.paragraphs]
    return "\n".join(paragraphs).strip()


def parse_resume(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """Returns (file_type, extracted_text)."""
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        text = parse_pdf(file_bytes)
        file_type = "pdf"
    elif lower_name.endswith(".docx"):
        text = parse_docx(file_bytes)
        file_type = "docx"
    else:
        raise UnsupportedFileTypeError(f"不支持的文件类型: {filename}")

    if not text.strip():
        raise EmptyResumeTextError("未能从文件中解析出任何文本,可能是扫描件或空文件")

    return file_type, text
