"""PDF/DOCX metin çıkarma. DOCX önce PDF'e çevrilip (rendering.py) aynı yoldan okunur."""

from pathlib import Path

import fitz  # PyMuPDF

from app.rendering import convert_docx_to_pdf


def extract_text_from_pdf(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def to_pdf(original_path: Path, work_dir: Path) -> Path:
    """Girdi dosyasını (pdf veya docx) her koşulda bir PDF yoluna çevirir."""
    suffix = original_path.suffix.lower()
    if suffix == ".pdf":
        return original_path
    if suffix in (".docx", ".doc"):
        return convert_docx_to_pdf(original_path, work_dir)
    raise ValueError(f"Desteklenmeyen dosya türü: {suffix}")
