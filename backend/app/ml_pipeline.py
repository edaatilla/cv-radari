"""CV işleme hattı: kategoriler, PDF/DOCX okuma, sayfa görüntüsü üretme, ML modelleri.

Model eğitimi yok — Hugging Face'ten hazır iki model kullanılıyor:
- sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (embedding: kategori + arama)
- savasy/bert-base-turkish-ner-cased (Türkçe NER: aday adı çıkarma)
"""

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

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


# ---------------------------------------------------------------------------
# Metin çıkarma
# ---------------------------------------------------------------------------

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
