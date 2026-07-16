"""Hugging Face Spaces (Gradio SDK, kartsız/ücretsiz) giriş noktası.

Docker gerektirmeden çalışır: bağımlılıklar requirements.txt (-r backend/requirements.txt)
ve packages.txt (libreoffice) üzerinden kurulur, bu dosya da FastAPI uygulamasını
doğrudan uvicorn ile ayağa kaldırır (Gradio hiç kullanılmıyor, sadece SDK'nın
kart istemeyen ücretsiz ortamından faydalanıyoruz).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.main import app as fastapi_app  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(fastapi_app, host="0.0.0.0", port=7860)
