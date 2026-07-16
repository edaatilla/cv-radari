---
title: CV Radarı Backend
emoji: 🗂️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# CV Radarı — Backend

CV'leri (PDF/DOCX) otomatik kategorize eden, arama sorgusuna göre en uygun adayı bulan ve
CV sayfalarını görüntü olarak sunan FastAPI servisi.

- Embedding + kategori/arama eşleştirme: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Aday adı çıkarma (Türkçe NER): `savasy/bert-base-turkish-ner-cased`
- DOCX → PDF: LibreOffice (headless)

Arayüz (`backend/static/index.html`) da bu Space'in kendisinden `/` yolunda servis edilir —
ayrı bir GitHub Pages barındırmasına gerek yok, tek link her şeyi kapsar. Bu Space uyandığında
(soğuk başlangıç) ilk istek birkaç saniye sürebilir, ücretsiz katmanda yeniden başlatıldığında
yüklenen CV'ler silinir (demo amaçlı, kalıcı depolama yok).

API dokümantasyonu: `/docs`
