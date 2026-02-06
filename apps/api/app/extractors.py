from pathlib import Path

import pdfplumber
from docx import Document

def extract_text_from_pdf(path: Path) -> str:
    text_parts = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t)
    return "\n".join(text_parts).strip()

def extract_text_from_docx(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join([p.text for p in doc.paragraphs]).strip()

def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    # For now we won’t support .doc without extra libs
    raise ValueError(f"Unsupported file type: {suffix}")
