# Hugging Face Spaces (Docker SDK) için — resmi HF örneğindeki 1000 UID kullanıcı deseni.
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user backend/app ./app
COPY --chown=user backend/static ./static

# Modelleri build zamanında indirip image'a göm — çalışma anında (soğuk başlangıçta) tekrar indirmesin.
RUN python -m app.download_models

RUN mkdir -p storage/uploads storage/renders

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
