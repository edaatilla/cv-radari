"""Hazır iki Hugging Face modeli (eğitim yok): embedding + Türkçe NER."""

import re
from functools import lru_cache

import numpy as np

from app.categories import CATEGORIES, CATEGORY_KEYS

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
    name = best["word"].strip()
    name = re.sub(r"\s+", " ", name)
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

    strong_text = ", ".join(strong) + " alanlarında"
    grow_text = ", ".join(grow) + " alanlarında"
    return strong_text, grow_text
