"""CV Radarı — tek dosyalık FastAPI backend + Hugging Face Spaces giriş noktası.

CV'leri (PDF/DOCX) otomatik kategorize eder, arama sorgusuna göre en uygun adayı bulur,
CV sayfalarını görüntü olarak sunar. Model eğitimi yok — iki hazır Hugging Face modeli
kullanılıyor:
  - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (embedding: kategori + arama)
  - savasy/bert-base-turkish-ner-cased (Türkçe NER: aday adı çıkarma)
LibreOffice (packages.txt ile kurulu) DOCX -> PDF dönüşümü için kullanılıyor.
"""

import json
import re
import shutil
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_PATH = BASE_DIR / "index.html"
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERS_DIR = STORAGE_DIR / "renders"
DB_PATH = STORAGE_DIR / "cvradar.db"

# ---------------------------------------------------------------------------
# Kategoriler (sabit, frontend'deki anahtarlarla birebir aynı)
# ---------------------------------------------------------------------------

CATEGORIES = {
    "tek": {
        "name": "Teknoloji",
        "description": (
            "Yazılım geliştirme, veri mühendisliği, bilgisayar mühendisliği, bulut altyapısı "
            "ve bilgi teknolojileri alanında çalışan bir profesyonel."
        ),
        "skills": [
            "Python", "Java", "JavaScript", "SQL", "Docker", "Kubernetes", "AWS", "Azure",
            "Spring", "React", "Node.js", "Airflow", "ETL", "Makine Öğrenmesi", "Bulut Altyapısı",
            "Mikroservis", "CI/CD", "Test Otomasyonu", "Veri Mühendisliği", "Backend", "Frontend",
        ],
    },
    "sag": {
        "name": "Sağlık",
        "description": (
            "Hastane, klinik veya sağlık kuruluşunda hasta bakımı, hemşirelik ya da tıbbi "
            "hizmetler alanında çalışan bir sağlık profesyoneli."
        ),
        "skills": [
            "Klinik Bakım", "Acil Servis", "Hasta İletişimi", "Hemşirelik", "Tıbbi Cihaz",
            "Ameliyathane", "Yoğun Bakım", "Hasta Kayıt Sistemleri", "Dijital Sağlık Kayıt",
            "İlk Yardım", "Enfeksiyon Kontrolü", "Sağlık Mevzuatı",
        ],
    },
    "egt": {
        "name": "Eğitim",
        "description": (
            "Okul veya akademik kurumda öğretmenlik, eğitim programı geliştirme ya da "
            "öğrenci değerlendirme alanında çalışan bir eğitim profesyoneli."
        ),
        "skills": [
            "Müfredat Geliştirme", "Sınıf Yönetimi", "Ölçme-Değerlendirme", "Eğitim Programı",
            "Uzaktan Eğitim", "Akademik Danışmanlık", "Eğitim Teknolojileri", "Rehberlik",
            "Ders Planlama", "Proje Tabanlı Öğrenme",
        ],
    },
    "fin": {
        "name": "Finans",
        "description": (
            "Muhasebe, finansal analiz, bütçeleme veya bankacılık alanında çalışan bir "
            "finans profesyoneli."
        ),
        "skills": [
            "Excel", "Bütçeleme", "Raporlama", "Finansal Modelleme", "Muhasebe", "Bankacılık",
            "Risk Yönetimi", "Denetim", "Veri Görselleştirme", "Vergi Mevzuatı", "Yatırım Analizi",
        ],
    },
    "paz": {
        "name": "Pazarlama",
        "description": (
            "Dijital pazarlama, marka yönetimi, kampanya optimizasyonu veya satış alanında "
            "çalışan bir pazarlama profesyoneli."
        ),
        "skills": [
            "SEO", "Kampanya Yönetimi", "Sosyal Medya", "İçerik Stratejisi", "Marka Yönetimi",
            "Performans Pazarlaması", "Google Ads", "Satış", "Müşteri İlişkileri Yönetimi",
            "Pazar Araştırması",
        ],
    },
}

CATEGORY_KEYS = list(CATEGORIES.keys())


# ---------------------------------------------------------------------------
# DOCX -> PDF (LibreOffice headless) ve PDF -> PNG sayfa görüntüleri
# ---------------------------------------------------------------------------

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
        "kurulmalı."
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


# ---------------------------------------------------------------------------
# ML: embedding (kategori + arama) ve Türkçe NER (ad çıkarma)
# ---------------------------------------------------------------------------

EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
NER_MODEL_NAME = "savasy/bert-base-turkish-ner-cased"

_embedder = None
_ner_pipeline = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedder


def get_ner_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline

        _ner_pipeline = pipeline(
            "ner",
            model=NER_MODEL_NAME,
            tokenizer=NER_MODEL_NAME,
            aggregation_strategy="simple",
        )
    return _ner_pipeline


def embed(text: str) -> np.ndarray:
    vec = get_embedder().encode(text, normalize_embeddings=True)
    return np.asarray(vec, dtype=np.float32)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


@lru_cache(maxsize=1)
def _category_embeddings() -> dict[str, np.ndarray]:
    return {key: embed(CATEGORIES[key]["description"]) for key in CATEGORY_KEYS}


@lru_cache(maxsize=None)
def _skill_embedding(skill: str) -> np.ndarray:
    return embed(skill)


def classify_category(text: str) -> tuple[str, float]:
    text_emb = embed(text[:2000])
    cat_embs = _category_embeddings()
    scores = {key: cosine_sim(text_emb, emb) for key, emb in cat_embs.items()}
    best_key = max(scores, key=scores.get)
    return best_key, scores[best_key]


def tags_for_category(text: str, category_key: str) -> list[str]:
    lowered = text.lower()
    skills = CATEGORIES[category_key]["skills"]
    return [s for s in skills if s.lower() in lowered]


FALLBACK_STOPWORDS = {"cv", "ozgecmis", "özgeçmiş", "resume", "muh", "mühendis"}


def fallback_name_from_filename(filename: str) -> str:
    base = re.sub(r"\.[^.]+$", "", filename)
    base = re.sub(r"^cv[_\-\s]*", "", base, flags=re.IGNORECASE)
    words = [w for w in re.split(r"[_\-\s]+", base) if w and w.lower() not in FALLBACK_STOPWORDS]
    name = " ".join(w[:1].upper() + w[1:] for w in words[:2])
    return name or "İsimsiz Aday"


def extract_name(text: str, filename: str) -> str:
    snippet = text[:800].strip()
    if not snippet:
        return fallback_name_from_filename(filename)
    try:
        entities = get_ner_pipeline()(snippet)
    except Exception:
        return fallback_name_from_filename(filename)

    people = [e for e in entities if e.get("entity_group") == "PER" and e.get("word", "").strip()]
    if not people:
        return fallback_name_from_filename(filename)

    best = max(people, key=lambda e: len(e["word"]))
    name = re.sub(r"\s+", " ", best["word"].strip())
    if len(name) < 3:
        return fallback_name_from_filename(filename)
    return name


def search_score(query_emb: np.ndarray, cv_emb: np.ndarray) -> int:
    sim = cosine_sim(query_emb, cv_emb)
    scaled = max(0.0, min(1.0, (sim + 1) / 2))
    return int(round(scaled * 99))


def strong_grow_notes(text: str, category_key: str, query: str | None) -> tuple[str, str]:
    skills = CATEGORIES[category_key]["skills"]
    present = set(tags_for_category(text, category_key))
    reference_text = query.strip() if query and query.strip() else CATEGORIES[category_key]["description"]
    ref_emb = embed(reference_text)

    scored = [(skill, cosine_sim(ref_emb, _skill_embedding(skill))) for skill in skills]
    scored.sort(key=lambda x: x[1], reverse=True)

    strong = [s for s, _ in scored if s in present][:3]
    grow = [s for s, _ in scored if s not in present][:2]

    if not strong:
        strong = [s for s, _ in scored[:2]]
    if not grow:
        grow = [s for s, _ in scored[-2:]]

    return ", ".join(strong) + " alanlarında", ", ".join(grow) + " alanlarında"


# ---------------------------------------------------------------------------
# Veritabanı (düz sqlite3, ORM yok)
# ---------------------------------------------------------------------------

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
        pdf_path = to_pdf(original_path, work_dir)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise HTTPException(422, f"{filename}: dosyadan metin çıkarılamadı (taranmış görüntü olabilir).")

    page_count = get_page_count(pdf_path)
    render_pdf_pages(pdf_path, work_dir, base_name=file_id)
    thumb_path = render_thumbnail(pdf_path, work_dir, base_name=file_id)

    category_key, category_score = classify_category(text)
    name = extract_name(text, filename)
    tags = tags_for_category(text, category_key)
    embedding = embed(text[:2000]).tolist()

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
            strong, grow = strong_grow_notes(c["raw_text"], c["category_key"], None)
            match = int(round(c["category_score"] * 99))
            results.append(_cv_to_dict(c, match=match, strong=strong, grow=grow))
        results.sort(key=lambda r: r["match"], reverse=True)
        return results

    query_emb = embed(req.query)
    scored = []
    for c in cvs:
        cv_emb = np.array(json.loads(c["embedding"]), dtype=np.float32)
        match = search_score(query_emb, cv_emb)
        strong, grow = strong_grow_notes(c["raw_text"], c["category_key"], req.query)
        scored.append(_cv_to_dict(c, match=match, strong=strong, grow=grow))

    scored.sort(key=lambda r: r["match"], reverse=True)
    return scored


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
