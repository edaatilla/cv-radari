"""FastAPI uygulaması: API uçları + SQLite veritabanı (düz sqlite3, ORM yok)."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import ml_pipeline as ml
from app.ml_pipeline import CATEGORIES, CATEGORY_KEYS

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERS_DIR = STORAGE_DIR / "renders"
FRONTEND_PATH = Path(__file__).resolve().parent.parent / "static" / "index.html"
DB_PATH = STORAGE_DIR / "cvradar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cvs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    name TEXT NOT NULL,
    category_key TEXT NOT NULL,
    category_score REAL NOT NULL,
    raw_text TEXT NOT NULL,
    embedding TEXT NOT NULL,
    tags TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    thumbnail_path TEXT,
    pages_dir TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(SCHEMA)


def insert_cv(**fields) -> int:
    fields["tags"] = json.dumps(fields["tags"], ensure_ascii=False)
    fields["embedding"] = json.dumps(fields["embedding"])
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    with get_conn() as conn:
        cur = conn.execute(f"INSERT INTO cvs ({columns}) VALUES ({placeholders})", tuple(fields.values()))
        return cur.lastrowid


def get_cv(cv_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()


def list_cvs() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM cvs ORDER BY created_at DESC").fetchall()


# ---------------------------------------------------------------------------
# FastAPI uygulaması
# ---------------------------------------------------------------------------

app = FastAPI(title="CV Radarı API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def frontend():
    return FileResponse(FRONTEND_PATH, media_type="text/html")


def _base_name(cv) -> str:
    return Path(cv["thumbnail_path"]).stem.removesuffix("_thumb")


def _cv_to_dict(cv, match: int | None = None, strong: str | None = None, grow: str | None = None) -> dict:
    cat = CATEGORIES[cv["category_key"]]
    return {
        "id": cv["id"],
        "name": cv["name"],
        "role": f"{cat['name']} Adayı",
        "cat": cv["category_key"],
        "category_name": cat["name"],
        "tags": json.loads(cv["tags"]),
        "page_count": cv["page_count"],
        "thumbnail_url": f"/api/cvs/{cv['id']}/thumbnail.png",
        "match": match,
        "strong": strong,
        "grow": grow,
    }


def process_upload(file_bytes: bytes, filename: str) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".doc"):
        raise HTTPException(400, f"Desteklenmeyen dosya türü: {suffix}")

    file_id = uuid.uuid4().hex
    original_path = UPLOADS_DIR / f"{file_id}{suffix}"
    original_path.write_bytes(file_bytes)

    work_dir = RENDERS_DIR / file_id
    try:
        pdf_path = ml.to_pdf(original_path, work_dir)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    text = ml.extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise HTTPException(422, f"{filename}: dosyadan metin çıkarılamadı (taranmış görüntü olabilir).")

    page_count = ml.get_page_count(pdf_path)
    ml.render_pdf_pages(pdf_path, work_dir, base_name=file_id)
    thumb_path = ml.render_thumbnail(pdf_path, work_dir, base_name=file_id)

    category_key, category_score = ml.classify_category(text)
    name = ml.extract_name(text, filename)
    tags = ml.tags_for_category(text, category_key)
    embedding = ml.embed(text[:2000]).tolist()

    cv_id = insert_cv(
        filename=filename,
        original_path=str(original_path),
        name=name,
        category_key=category_key,
        category_score=category_score,
        raw_text=text,
        embedding=embedding,
        tags=tags,
        page_count=page_count,
        thumbnail_path=str(thumb_path),
        pages_dir=str(work_dir),
    )
    return _cv_to_dict(get_cv(cv_id))


@app.post("/api/cvs")
async def upload_cvs(files: list[UploadFile]):
    results = []
    for f in files:
        content = await f.read()
        results.append(process_upload(content, f.filename))
    return results


@app.get("/api/categories")
def get_categories():
    cvs = list_cvs()
    out = []
    for key in CATEGORY_KEYS:
        cat = CATEGORIES[key]
        items = [_cv_to_dict(c) for c in cvs if c["category_key"] == key]
        out.append({"key": key, "name": cat["name"], "count": len(items), "cvs": items})
    return out


@app.get("/api/cvs/{cv_id}")
def get_cv_detail(cv_id: int):
    cv = get_cv(cv_id)
    if cv is None:
        raise HTTPException(404, "CV bulunamadı")
    result = _cv_to_dict(cv)
    result["raw_text"] = cv["raw_text"]
    result["category_score"] = cv["category_score"]
    return result


@app.get("/api/cvs/{cv_id}/thumbnail.png")
def get_thumbnail(cv_id: int):
    cv = get_cv(cv_id)
    if cv is None or not cv["thumbnail_path"] or not Path(cv["thumbnail_path"]).exists():
        raise HTTPException(404, "Küçük görüntü bulunamadı")
    return FileResponse(cv["thumbnail_path"], media_type="image/png")


@app.get("/api/cvs/{cv_id}/pages/{page_num}.png")
def get_page(cv_id: int, page_num: int):
    cv = get_cv(cv_id)
    if cv is None:
        raise HTTPException(404, "CV bulunamadı")
    page_path = Path(cv["pages_dir"]) / f"{_base_name(cv)}_page{page_num}.png"
    if not page_path.exists():
        raise HTTPException(404, "Sayfa görüntüsü bulunamadı")
    return FileResponse(page_path, media_type="image/png")


class SearchRequest(BaseModel):
    query: str = ""


@app.post("/api/search")
def search(req: SearchRequest):
    cvs = list_cvs()
    if not req.query.strip():
        results = []
        for c in cvs:
            strong, grow = ml.strong_grow_notes(c["raw_text"], c["category_key"], None)
            match = int(round(c["category_score"] * 99))
            results.append(_cv_to_dict(c, match=match, strong=strong, grow=grow))
        results.sort(key=lambda r: r["match"], reverse=True)
        return results

    query_emb = ml.embed(req.query)
    scored = []
    for c in cvs:
        cv_emb = np.array(json.loads(c["embedding"]), dtype=np.float32)
        match = ml.search_score(query_emb, cv_emb)
        strong, grow = ml.strong_grow_notes(c["raw_text"], c["category_key"], req.query)
        scored.append(_cv_to_dict(c, match=match, strong=strong, grow=grow))

    scored.sort(key=lambda r: r["match"], reverse=True)
    return scored
