import json
import uuid
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import db, extraction, ml, rendering
from app.categories import CATEGORIES, CATEGORY_KEYS

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERS_DIR = STORAGE_DIR / "renders"

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
    db.init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


def _base_name(cv) -> str:
    thumb_stem = Path(cv["thumbnail_path"]).stem
    return thumb_stem.removesuffix("_thumb")


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
        pdf_path = extraction.to_pdf(original_path, work_dir)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    text = extraction.extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise HTTPException(422, f"{filename}: dosyadan metin çıkarılamadı (taranmış görüntü olabilir).")

    page_count = rendering.get_page_count(pdf_path)
    rendering.render_pdf_pages(pdf_path, work_dir, base_name=file_id)
    thumb_path = rendering.render_thumbnail(pdf_path, work_dir, base_name=file_id)

    category_key, category_score = ml.classify_category(text)
    name = ml.extract_name(text, filename)
    tags = ml.tags_for_category(text, category_key)
    embedding = ml.embed(text[:2000]).tolist()

    cv_id = db.insert_cv(
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
    return _cv_to_dict(db.get_cv(cv_id))


@app.post("/api/cvs")
async def upload_cvs(files: list[UploadFile]):
    results = []
    for f in files:
        content = await f.read()
        results.append(process_upload(content, f.filename))
    return results


@app.get("/api/categories")
def get_categories():
    cvs = db.list_cvs()
    out = []
    for key in CATEGORY_KEYS:
        cat = CATEGORIES[key]
        items = [_cv_to_dict(c) for c in cvs if c["category_key"] == key]
        out.append({"key": key, "name": cat["name"], "count": len(items), "cvs": items})
    return out


@app.get("/api/cvs/{cv_id}")
def get_cv_detail(cv_id: int):
    cv = db.get_cv(cv_id)
    if cv is None:
        raise HTTPException(404, "CV bulunamadı")
    result = _cv_to_dict(cv)
    result["raw_text"] = cv["raw_text"]
    result["category_score"] = cv["category_score"]
    return result


@app.get("/api/cvs/{cv_id}/thumbnail.png")
def get_thumbnail(cv_id: int):
    cv = db.get_cv(cv_id)
    if cv is None or not cv["thumbnail_path"] or not Path(cv["thumbnail_path"]).exists():
        raise HTTPException(404, "Küçük görüntü bulunamadı")
    return FileResponse(cv["thumbnail_path"], media_type="image/png")


@app.get("/api/cvs/{cv_id}/pages/{page_num}.png")
def get_page(cv_id: int, page_num: int):
    cv = db.get_cv(cv_id)
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
    cvs = db.list_cvs()
    if not req.query.strip():
        results = [_cv_to_dict(c, match=None, strong=None, grow=None) for c in cvs]
        for r in results:
            strong, grow = ml.strong_grow_notes(
                next(c["raw_text"] for c in cvs if c["id"] == r["id"]), r["cat"], None
            )
            r["strong"], r["grow"] = strong, grow
            r["match"] = int(round(next(c["category_score"] for c in cvs if c["id"] == r["id"]) * 99))
        results.sort(key=lambda r: r["match"], reverse=True)
        return results

    query_emb = ml.embed(req.query)
    scored = []
    for c in cvs:
        cv_emb = json.loads(c["embedding"])
        match = ml.search_score(query_emb, np.array(cv_emb, dtype=np.float32))
        strong, grow = ml.strong_grow_notes(c["raw_text"], c["category_key"], req.query)
        scored.append(_cv_to_dict(c, match=match, strong=strong, grow=grow))

    scored.sort(key=lambda r: r["match"], reverse=True)
    return scored
