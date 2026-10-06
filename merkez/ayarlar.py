"""Ayarlar: site profilleri + genel (sağlayıcı/model/veritabanı) ayarları.

Ayarlar iki dosyada tutulur:
  profiller/<profil>.json  -> siteye özgü her şey (adres, ad, keşif kuralları,
                                      test parametreleri, AI talimatındaki site tanımı ...)
  ayarlar.json             -> genel ayarlar ve etkin profil (git dışı)

Program içinde ikisi tek sözlükte birleşir; kaydederken anahtarlar ait oldukları
dosyaya ayrılır. Yollar göreli verilirse repo köküne göre çözülür, böylece profil
dosyaları başka bilgisayarda da çalışır.
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import yollar

# ------------------------------------------------------------- site profili
PROFIL_VARSAYILAN = {
    "site_adi": "Yeni site",
    "site_url": "https://ornek.com/",
    "cikti_koku": "ciktilar/yeni-site",
    "harita": "ciktilar/yeni-site/kesif/site_haritasi.json",
    # Tarayıcı ve raporlar
    "locale": "tr-TR",
    "user_agent": "",
    # Yapay zekâ talimatı (İngilizce yazılır, modele gider)
    "site_tanimi": "a website",
    "site_dili": "Turkish",
    # Keşif (tools/kesif.py)
    "kesif_tarayici": False,
    "kesif_ssl_yoksay": True,
    "kesif_max_sayfa": 20000,
    "kesif_derinlik": 0,
    "kesif_isci": 4,
    "kesif_rps": 5.0,
    "kesif_haric": "",
    "kesif_dahil": "",
    "kesif_yoksay_param": "utm_source utm_medium utm_campaign fbclid gclid sessionid",
    "kesif_sorgu_limiti": 50,
    "kesif_sitemap": True,
    "kesif_robots": False,
    "kesif_alt_alanlar": False,
    # Web testi (tester_v3_evidence.py)
    "esz": 4,
    "zaman_asimi": 30,
    "deneme_limit": 50,
    "parca": 2000,
    "taze_basla": False,
    "tablet": False,
    "gorunur": False,
    # Denetim ve doğrulama
    "temsilci_sayisi": 3,
    "rota_limit": 0,
    "tiklama_limit": 40,
    # Görsel doğrulama ve düzeltme (gorsel-denetim 7-10. aşamalar)
    "etiket_ornek": 30,
    "etiket_csv": "",            # boş = İndirilenler/etiketler.csv
    "css_oneri": "",             # boş = otomatik düzeltmenin oneri.css'i, yoksa tools/visual_audit/oneri.css
    "oto_limit": 200,
    "oto_cihaz": "mobile",
    "oto_tur": 4,
    "oto_goruntu": 12,
    # Bologna (OİBS kullanan herhangi bir üniversite)
    "bologna_url": "https://obs.mersin.edu.tr/oibs/bologna/",
    "bologna_program": "1371",
    "bologna_seviye": "lisans",
}

# ------------------------------------------------------------- genel ayarlar
GENEL_VARSAYILAN = {
    "aktif_profil": "meu-oidb",
    "python": sys.executable,
    "hata_olursa_devam": False,
    "ayrintili": False,
    # sade: yerleşik tema, hızlı çizim (varsayılan) | modern: sv-ttk (Windows 11 görünümü).
    # sv-ttk her öğeyi saydam resimlerle çizer; Windows'ta ölçümde sayfa geçişi 5-7 kat,
    # tema değişimi ~5 kat yavaş çıktı. (Eski 'gorunum' anahtarı bilerek okunmaz.)
    "arayuz_gorunumu": "sade",
    "tema": "light",             # arayüz: light | dark          # hata ayıklama: komut ayrıntıları + Bologna -v
    # Sağlayıcılar
    "anthropic_key": "",
    "claude_model": "claude-opus-5",
    "claude_effort": "",
    "gemini_key": "",
    "gemini_model": "gemini-3.6-flash",
    "openai_url": "https://api.openai.com/v1",
    "openai_key": "",
    "openai_model": "gpt-5-mini",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5vl:3b",       # visual_ai_review.py varsayılanı
    "anahtarlari_kaydet": False,
    # Analiz hattı: görsel denetimde fiilen kullanılan modeller (ai_v2 turu; rapor.py ve
    # isabet.py varsayılanlarıyla aynı). Ana tarama Gemma 4, hakem Gemini Flash Lite.
    "ai_modeller": "gemini:gemma-4-31b-it",
    "ai_limit": 0,
    "ai_dakika_limit": 8,
    "ai_paralel": 4,
    "ai_hakem": "gemini:gemini-3.5-flash-lite",
    "ai_hakem_ornek": 0,
    "ai_hakem_grup": "tur",
    "ai_toplu": False,
    "ai_ana": "gemini:gemma-4-31b-it",
    "ai_isabet_hakem": "gemini:gemini-3.5-flash-lite",
    # Bologna veritabanı
    "bologna_mod": "docker",
    "bologna_db": "postgres://bologna:bologna@localhost:5432/bologna?sslmode=disable",
    "bologna_havuz": True,
    "bologna_yillar": "1",
    "bologna_isci": 2,
    "bologna_rps": 2.0,
}

VARSAYILAN = {**PROFIL_VARSAYILAN, **GENEL_VARSAYILAN}
ANAHTARLAR = ("anthropic_key", "gemini_key", "openai_key")

# OpenAI uyumlu servisler için hazır adresler (arayüzde seçilebilir)
OPENAI_HAZIR = {
    "OpenAI": "https://api.openai.com/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "Mistral": "https://api.mistral.ai/v1",
    "Together": "https://api.together.xyz/v1",
    "LM Studio (yerel)": "http://localhost:1234/v1",
    "Ollama (OpenAI uyumlu)": "http://localhost:11434/v1",
    "vLLM (yerel)": "http://localhost:8000/v1",
}


# ------------------------------------------------------------- yardımcılar

def profil_kimligi(ad: str) -> str:
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    k = re.sub(r"[^a-z0-9]+", "-", ad.translate(tablo).lower()).strip("-")
    return k or "site"


def yol(deger) -> Path:
    """Göreli yolları repo köküne göre çöz."""
    p = Path(str(deger)).expanduser()
    return p if p.is_absolute() else yollar.REPO / p


def _gorelilestir(p) -> str:
    try:
        return Path(p).resolve().relative_to(yollar.REPO).as_posix()
    except ValueError:
        return str(p)


def _uygula(hedef: dict, kaynak: dict, sablon: dict) -> None:
    for k, v in kaynak.items():
        if k not in sablon:
            continue
        beklenen = type(sablon[k])
        if beklenen is float and isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        if type(v) is beklenen:
            hedef[k] = v


def profil_dosyasi(profil: str, klasor: Path = None) -> Path:
    return (klasor or yollar.PROFILLER) / f"{profil}.json"


def profiller(klasor: Path = None) -> list:
    k = klasor or yollar.PROFILLER
    return sorted(p.stem for p in k.glob("*.json")) if k.exists() else []


def profil_oku(profil: str, klasor: Path = None) -> dict:
    ayar = dict(PROFIL_VARSAYILAN)
    try:
        _uygula(ayar, json.loads(profil_dosyasi(profil, klasor).read_text(encoding="utf-8")),
                PROFIL_VARSAYILAN)
    except (OSError, ValueError):
        pass
    return ayar


def yukle(dosya: Path = None, profil_klasoru: Path = None, profil: str = None) -> dict:
    ayar = dict(VARSAYILAN)
    try:
        _uygula(ayar, json.loads(Path(dosya or yollar.AYAR_DOSYASI).read_text(encoding="utf-8")),
                GENEL_VARSAYILAN)
    except (OSError, ValueError):
        pass
    if profil:
        ayar["aktif_profil"] = profil
    mevcut = profiller(profil_klasoru)
    if ayar["aktif_profil"] not in mevcut and mevcut:
        ayar["aktif_profil"] = mevcut[0]
    ayar.update(profil_oku(ayar["aktif_profil"], profil_klasoru))
    if not Path(ayar["python"]).exists():   # repo başka bilgisayara taşındıysa
        ayar["python"] = sys.executable
    return ayar


def kaydet(ayar: dict, dosya: Path = None, profil_klasoru: Path = None) -> None:
    genel = {k: ayar[k] for k in GENEL_VARSAYILAN if k in ayar}
    if not genel.get("anahtarlari_kaydet"):
        for k in ANAHTARLAR:
            genel[k] = ""
    Path(dosya or yollar.AYAR_DOSYASI).write_text(
        json.dumps(genel, ensure_ascii=False, indent=2), encoding="utf-8")
    profil_kaydet(ayar, ayar["aktif_profil"], profil_klasoru)


def profil_kaydet(ayar: dict, profil: str, klasor: Path = None) -> Path:
    veri = {k: ayar[k] for k in PROFIL_VARSAYILAN if k in ayar}
    for k in ("cikti_koku", "harita"):
        veri[k] = _gorelilestir(yol(veri[k]))
    d = profil_dosyasi(profil, klasor)
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def yeni_profil(ad: str, url: str, site_adi: str = "", klasor: Path = None) -> str:
    """Yeni site için profil oluşturur; çıktılar ciktilar/<profil>/ altına gider."""
    kimlik = profil_kimligi(ad or urlparse(url).netloc)
    p = dict(PROFIL_VARSAYILAN)
    p.update({
        "site_adi": site_adi or ad or urlparse(url).netloc,
        "site_url": url,
        "cikti_koku": f"ciktilar/{kimlik}",
        "harita": f"ciktilar/{kimlik}/kesif/site_haritasi.json",
        "site_tanimi": f"the website {urlparse(url).netloc}",
    })
    profil_kaydet(p, kimlik, klasor)
    return kimlik


def etkin_ortam(ayar: dict) -> dict:
    """Alt süreçlere aktarılacak sağlayıcı anahtarları."""
    env = {}
    for anahtar, degisken in (("anthropic_key", "ANTHROPIC_API_KEY"),
                              ("gemini_key", "GEMINI_API_KEY"),
                              ("openai_key", "OPENAI_API_KEY")):
        if ayar.get(anahtar):
            env[degisken] = ayar[anahtar]
    if ayar.get("ollama_url"):
        env["OLLAMA_HOST"] = ayar["ollama_url"]
    return env


class Klasorler:
    """Etkin profilin çıktı köküne göre her aracın çıktı klasörü (ciktilar/<profil>/ ...).
    Şablon kümeleri site haritasının yanına yazılır."""

    def __init__(self, ayar: dict):
        self.kok = yol(ayar["cikti_koku"])
        self.harita = yol(ayar["harita"])
        self.veri = self.harita.parent          # şablon kümeleri haritanın yanına yazılır
        self.test = self.kok / "test_output"
        self.deneme = self.kok / "deneme_output"
        self.belge = self.kok / "denetim"
        self.link = self.kok / "linkdenetim"
        self.gorsel = self.kok / "gorsel"
        self.gorsel_ai = self.kok / "gorsel_ai"
        self.kesif_haritasi = self.kok / "kesif" / "site_haritasi.json"
        self.yeniden = self.kok / "yeniden_cekim"
        self.ai_kok = self.kok / "visual_audit"
        self.denetim_cikti = self.ai_kok / "denetim_cikti"
        self.ai_sonuc = self.denetim_cikti / "ai_v2"
        self.ai_rapor = self.denetim_cikti / "rapor"
        self.temsilci_urls = self.ai_kok / "temsilci_urls.json"
        self.metin_csv = self.ai_kok / "metin_kontrol.csv"
        self.rota_csv = self.kok / "routes_verification.csv"
        self.tiklama_csv = self.kok / "clicks_verification.csv"
        self.teslim = self.kok / "TESLIM"
        self.kayitlar = self.kok / "merkez_kayitlari"
        self.temsilciler = self.veri / "template_representatives.json"
        # Görsel doğrulama ve düzeltme
        self.dogrulama = self.kok / "dogrulama"
        self.dogrulama_css = self.kok / "dogrulama_css"
        self.dogrulama_cikti = self.ai_kok / "dogrulama_cikti"
        self.etiket = self.ai_kok / "etiket"
        self.css_cikti = self.ai_kok / "css_cikti"
        self.oto = self.ai_kok / "oto_cikti"
        self.kumeler = self.veri / "template_clusters.json"
