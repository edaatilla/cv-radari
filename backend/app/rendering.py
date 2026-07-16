"""DOCX -> PDF (LibreOffice headless) ve PDF -> PNG sayfa görüntüleri."""

import shutil
import subprocess
from pathlib import Path

import fitz  # PyMuPDF

THUMBNAIL_WIDTH = 360
PAGE_WIDTH = 1000


def find_soffice() -> str:
    exe = shutil.which("soffice") or shutil.which("soffice.exe")
    if exe:
        return exe
    common_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in common_paths:
        if Path(p).exists():
            return p
    raise RuntimeError(
        "LibreOffice (soffice) bulunamadı. DOCX dosyalarını işleyebilmek için LibreOffice "
        "kurulmalı. Windows'ta kurulum için: winget install TheDocumentFoundation.LibreOffice"
    )


def convert_docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
    soffice = find_soffice()
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(
            f"DOCX -> PDF dönüşümü başarısız oldu: {result.stderr or result.stdout}"
        )
    return pdf_path


def render_pdf_pages(pdf_path: Path, out_dir: Path, base_name: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    page_paths: list[Path] = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            zoom = PAGE_WIDTH / page.rect.width
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix)
            page_path = out_dir / f"{base_name}_page{i + 1}.png"
            pix.save(str(page_path))
            page_paths.append(page_path)
    finally:
        doc.close()
    return page_paths


def render_thumbnail(pdf_path: Path, out_dir: Path, base_name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = out_dir / f"{base_name}_thumb.png"
    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        zoom = THUMBNAIL_WIDTH / page.rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        pix.save(str(thumb_path))
    finally:
        doc.close()
    return thumb_path


def get_page_count(pdf_path: Path) -> int:
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()
