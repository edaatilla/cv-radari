"""Sabit kategori listesi: prototip (cv_radar_prototype.html) ile birebir aynı anahtarlar."""

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
