"""Docker build sırasında iki modeli önceden indirip image içine gömer (soğuk başlangıcı hızlandırır)."""

from app.ml import EMBEDDING_MODEL_NAME, NER_MODEL_NAME


def main():
    from sentence_transformers import SentenceTransformer
    from transformers import pipeline

    print(f"İndiriliyor: {EMBEDDING_MODEL_NAME}")
    SentenceTransformer(EMBEDDING_MODEL_NAME)

    print(f"İndiriliyor: {NER_MODEL_NAME}")
    pipeline("ner", model=NER_MODEL_NAME, tokenizer=NER_MODEL_NAME, aggregation_strategy="simple")

    print("Modeller indirildi.")


if __name__ == "__main__":
    main()
