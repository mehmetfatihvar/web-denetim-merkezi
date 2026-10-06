"""Staj boyunca yapılan her işin program içindeki karşılığı: adımlar.

Her adım, ayarlardan bir veya birkaç komut üretir. Komutlar repodaki mevcut
araçları (tools/, tools/visual_audit/, bologna-scraper/) değiştirmeden,
rehberlerdeki parametrelerle çalıştırır. Bu modül arayüzden bağımsızdır;
komut satırından ve testlerden de kullanılır.
"""

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import yollar
from .ayarlar import Klasorler, etkin_ortam, yol

WINDOWS = os.name == "nt"

# Sekmeler (arayüzdeki sıra)
GRUPLAR = [
    ("hazirlik", "Hazırlık"),
    ("web", "Web testi"),
    ("denetim", "Denetimler"),
    ("dogrulama", "Doğrulama"),
    ("ai", "Yapay zekâ denetimi"),
    ("duzeltme", "Doğrula ve düzelt"),
    ("bologna", "Bologna"),
    ("teslim", "Teslim"),
]


@dataclass
class Komut:
    """Çalıştırılacak tek iş: ya bir dış süreç (argv) ya da Python fonksiyonu."""
    argv: List[str] = field(default_factory=list)
    cwd: Path = yollar.REPO
    env: Dict[str, str] = field(default_factory=dict)
    fonksiyon: Optional[Callable[[Callable[[str], None]], int]] = None
    aciklama: str = ""

    def goster(self) -> str:
        if self.fonksiyon:
            return f"[program içi] {self.aciklama}"
        parcalar = [a if a and " " not in a else f'"{a}"' for a in self.argv]
        return f"({self.cwd}) " + " ".join(parcalar)


@dataclass
class Adim:
    id: str
    grup: str
    ad: str
    aciklama: str
    komutlar: Callable[[dict], List[Komut]]
    ciktilar: Callable[[dict], List[Path]] = lambda ayar: []
    sure: str = ""          # kullanıcıya tahmini süre bilgisi


# --------------------------------------------------------------- yardımcılar

def _py(ayar, betik, *argumanlar, cwd=yollar.ARACLAR, aciklama=""):
    return Komut([ayar["python"], "-u", str(betik), *map(str, argumanlar)], cwd=cwd,
                 aciklama=aciklama)


_ONBELLEK = {}
_ONBELLEK_KILIT = threading.Lock()


def onbellekli(yol: Path, oku):
    """Dosyadan türetilen değeri, dosya değişene kadar (boyut + zaman) yeniden okumadan verir.

    Site haritası ve test sonuçları onbinlerce kayıt olabilir; arayüz her sayfa açılışında
    bunları baştan okursa takılır.
    """
    try:
        st = Path(yol).stat()
    except OSError:
        return oku(yol)
    anahtar = (str(yol), oku.__name__)
    imza = (st.st_mtime_ns, st.st_size)
    with _ONBELLEK_KILIT:
        kayit = _ONBELLEK.get(anahtar)
    if kayit and kayit[0] == imza:
        return kayit[1]
    deger = oku(yol)
    with _ONBELLEK_KILIT:
        _ONBELLEK[anahtar] = (imza, deger)
    return deger


def harita_url_sayisi(harita: Path) -> int:
    """Site haritasındaki URL sayısı (tester'ın okuduğu biçimlerin hepsi)."""
    return onbellekli(harita, _harita_say)


def _harita_say(harita: Path) -> int:
    try:
        veri = json.loads(Path(harita).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(veri, dict):
        for anahtar in ("url_list", "pages", "urls"):
            if anahtar in veri:
                return len(veri[anahtar])
    return len(veri) if isinstance(veri, (list, dict)) else 0


def _site_secenekleri(ayar):
    """Tester'a giden siteye özgü seçenekler (rapor adı, yerel ayar, User-Agent)."""
    s = ["--site-adi", ayar["site_adi"], "--locale", ayar["locale"]]
    if ayar["user_agent"]:
        s += ["--user-agent", ayar["user_agent"]]
    return s


def _tester(ayar, out_dir, *ek, source=None):
    a = ["--source", source or yol(ayar["harita"]), "--out-dir", out_dir,
         "--concurrency", ayar["esz"], "--timeout", ayar["zaman_asimi"], *ek,
         *_site_secenekleri(ayar)]
    if ayar["gorunur"]:
        a.append("--headed")
    return _py(ayar, "tester_v3_evidence.py", *a)


def _bologna(ayar, *argumanlar, aciklama=""):
    """Bologna CLI komutu: Docker ile veya yerelde derlenmiş Go ikilisiyle."""
    argumanlar = (*argumanlar, "--base-url", ayar["bologna_url"],
                  *(["-v"] if ayar.get("ayrintili") else []))
    if ayar["bologna_mod"] == "docker":
        return [Komut(["docker", "compose", "--profile", "scrape", "run", "--rm", "scraper",
                       *argumanlar], cwd=yollar.BOLOGNA, aciklama=aciklama)]
    ikili = str(Path("bin") / ("bologna.exe" if WINDOWS else "bologna"))
    return [
        Komut(["go", "build", "-o", ikili, "./cmd/bologna"], cwd=yollar.BOLOGNA,
              aciklama="Bologna CLI'yi derle"),
        Komut([str(yollar.BOLOGNA / ikili), *argumanlar], cwd=yollar.BOLOGNA,
              env={"BOLOGNA_DB_URL": ayar["bologna_db"]}, aciklama=aciklama),
    ]


def _bologna_tarama_secenekleri(ayar):
    s = ["--workers", str(ayar["bologna_isci"]), "--rps", f'{ayar["bologna_rps"]:g}']
    if ayar["bologna_havuz"]:
        s.append("--pool-details")
    if ayar["bologna_yillar"].strip() not in ("", "1"):
        s += ["--years", ayar["bologna_yillar"].strip()]
    return s


def _analiz(ayar, *ek, aciklama=""):
    k = Klasorler(ayar)
    a = ["--ornekler", k.denetim_cikti / "ornekler.csv", "--cikti", k.ai_sonuc,
         "--klasor", k.yeniden / "screenshots",
         "--site-tanimi", ayar["site_tanimi"], "--site-dili", ayar["site_dili"],
         "--claude-model", ayar["claude_model"], "--gemini-model", ayar["gemini_model"],
         "--openai-url", ayar["openai_url"], "--paralel", ayar["ai_paralel"]]
    if ayar["claude_effort"]:
        a += ["--claude-effort", ayar["claude_effort"]]
    if ayar["ai_limit"]:
        a += ["--limit", ayar["ai_limit"]]
    if ayar["ai_dakika_limit"]:
        a += ["--dakika-limit", ayar["ai_dakika_limit"]]
    komut = _py(ayar, "analiz.py", *a, *ek, cwd=yollar.GORSEL_DENETIM, aciklama=aciklama)
    komut.env.update(etkin_ortam(ayar))
    return komut


# ----------------------------------------------------------------- komutlar

def _kurulum(ayar):
    return [
        Komut([ayar["python"], "-m", "pip", "install", "-r", str(yollar.REPO / "requirements.txt")],
              aciklama="Python paketlerini kur (requirements.txt)"),
        Komut([ayar["python"], "-m", "playwright", "install", "chromium"],
              aciklama="Chromium tarayıcısını indir"),
    ]


def kesif_argumanlari(ayar, cikti):
    a = ["--url", ayar["site_url"], "--cikti", cikti,
         "--max-sayfa", ayar["kesif_max_sayfa"], "--derinlik", ayar["kesif_derinlik"],
         "--isci", ayar["kesif_isci"], "--rps", f'{ayar["kesif_rps"]:g}',
         "--sorgu-limiti", ayar["kesif_sorgu_limiti"], "--dil", ayar["locale"]]
    for bayrak, anahtar in (("--tarayici", "kesif_tarayici"), ("--ssl-yoksay", "kesif_ssl_yoksay"),
                            ("--sitemap", "kesif_sitemap"), ("--robots", "kesif_robots"),
                            ("--alt-alanlar", "kesif_alt_alanlar")):
        if ayar[anahtar]:
            a.append(bayrak)
    for bayrak, anahtar in (("--haric", "kesif_haric"), ("--dahil", "kesif_dahil"),
                            ("--yoksay-param", "kesif_yoksay_param")):
        degerler = ayar[anahtar].split()
        if degerler or anahtar == "kesif_yoksay_param":
            a += [bayrak, *degerler]
    if ayar["user_agent"]:
        a += ["--user-agent", ayar["user_agent"]]
    return a


def _kesif(ayar):
    k = Klasorler(ayar)

    def hazirla(yaz):
        k.kesif_haritasi.parent.mkdir(parents=True, exist_ok=True)
        return 0
    return [Komut(fonksiyon=hazirla, aciklama="Keşif klasörünü hazırla"),
            _py(ayar, "kesif.py", *kesif_argumanlari(ayar, k.kesif_haritasi))]


def _kesif_kullan(ayar):
    k = Klasorler(ayar)
    yeni = k.kesif_haritasi

    def calis(yaz):
        if not yeni.exists():
            yaz(f"Yeni harita yok: {yeni}\nÖnce 'Site keşfi' adımını çalıştırın.\n")
            return 1
        ayar["harita"] = str(yeni)
        yaz(f"Artık bu harita kullanılacak ({harita_url_sayisi(yeni)} URL):\n{yeni}\n"
            "Kalıcı olması için Ayarlar sekmesinde 'Kaydet'e basın.\n")
        return 0
    return [Komut(fonksiyon=calis, aciklama="Keşif haritasını etkin harita yap")]


def _tam_test(ayar):
    k = Klasorler(ayar)
    toplam = harita_url_sayisi(yol(ayar["harita"]))
    parca = max(int(ayar["parca"]), 1)
    ek = ["--tablet"] if ayar["tablet"] else []
    if not toplam:
        return [_tester(ayar, k.test, *ek, *(["--fresh"] if ayar["taze_basla"] else []))]
    komutlar = []
    for bas in range(0, toplam, parca):
        taze = ["--fresh"] if ayar["taze_basla"] and bas == 0 else []
        c = _tester(ayar, k.test, "--offset", bas, "--limit", parca, *ek, *taze)
        c.aciklama = f"Parça {bas // parca + 1}: {bas}-{min(bas + parca, toplam)}"
        komutlar.append(c)
    return komutlar


def _ortam(ayar):
    from .ortam import rapor
    return [Komut(fonksiyon=lambda yaz: rapor(ayar, yaz), aciklama="Ortam kontrolü")]


def _saglayici(ayar):
    from .saglayicilar import test_et
    return [Komut(fonksiyon=lambda yaz: test_et(ayar, yaz), aciklama="Sağlayıcı bağlantı testi")]


def _tester_gorsel(ayar, kaynak, cikti, *ek):
    """Görsel doğrulama çekimi: DOM denetimi + kaydırma, her seferinde sıfırdan."""
    return _tester(ayar, cikti, "--check-visual", "--kaydir", "--fresh", *ek, source=str(kaynak))


def css_dosyasi(ayar) -> Path:
    """Denenecek CSS: ayarda verilen; yoksa otomatik düzeltmenin önerisi; o da yoksa
    gorsel-denetim'in ÖİDB için hazırladığı oneri.css."""
    if ayar["css_oneri"].strip():
        return yol(ayar["css_oneri"].strip())
    oto = Klasorler(ayar).oto / "oneri.css"
    return oto if oto.exists() else yollar.GORSEL_DENETIM / "oneri.css"


def etiket_csv(ayar) -> Path:
    return yol(ayar["etiket_csv"]) if ayar["etiket_csv"].strip() else \
        Path.home() / "Downloads" / "etiketler.csv"


def _dogrulama(ayar):
    k = Klasorler(ayar)
    gd = yollar.GORSEL_DENETIM
    urls = k.dogrulama_cikti / "dogrulama_urls.json"
    return [
        _py(ayar, "dogrulama.py", "hazirla", "--harita", yol(ayar["harita"]),
            "--tarama", k.denetim_cikti / "tarama.csv", "--ai", k.ai_sonuc, "--metin", k.metin_csv,
            "--http", k.yeniden / "http_hatali.csv", "--cikti", k.dogrulama_cikti, cwd=gd,
            aciklama="Hata bulunan sayfaları topla"),
        _tester_gorsel(ayar, urls, k.dogrulama),
        _py(ayar, "metin_kontrol.py", "--source", urls, "--cikti",
            k.dogrulama_cikti / "metin_yeniden.csv", cwd=gd, aciklama="Metin hatalarını yeniden ölç"),
        _py(ayar, "dogrulama.py", "karsilastir", "--dogrulama", k.dogrulama, "--metin-yeni",
            k.dogrulama_cikti / "metin_yeniden.csv", "--cikti", k.dogrulama_cikti, cwd=gd,
            aciklama="Eski bulguları yeni ölçümle karşılaştır"),
    ]


def _css_deneme(ayar):
    k = Klasorler(ayar)
    gd = yollar.GORSEL_DENETIM
    css = css_dosyasi(ayar)
    return [
        _py(ayar, "css_deneme.py", "hazirla", "--once", k.dogrulama, "--cikti", k.css_cikti, cwd=gd,
            aciklama="Yana kayan sayfaları seç"),
        _tester_gorsel(ayar, k.css_cikti / "css_urls.json", k.dogrulama_css, "--css", css),
        _py(ayar, "css_deneme.py", "karsilastir", "--once", k.dogrulama, "--sonra", k.dogrulama_css,
            "--cikti", k.css_cikti, cwd=gd, aciklama=f"CSS'siz / CSS'li karşılaştır ({css.name})"),
    ]


def _oto_duzelt(ayar):
    k = Klasorler(ayar)
    harita = yol(ayar["harita"])
    kaynak = ["--urls", harita] if harita_url_sayisi(harita) else ["--site", ayar["site_url"]]
    return [_py(ayar, "oto_duzelt.py", *kaynak, "--limit", ayar["oto_limit"], "--cihaz", ayar["oto_cihaz"],
                "--tur", ayar["oto_tur"], "--eszamanli", ayar["esz"], "--zaman-asimi", ayar["zaman_asimi"],
                "--goruntu", ayar["oto_goruntu"], "--cikti", k.oto, cwd=yollar.GORSEL_DENETIM)]


def _teslim(ayar):
    from .teslim import paketle
    return [Komut(fonksiyon=lambda yaz: paketle(Klasorler(ayar), yaz),
                  aciklama="TESLIM paketini oluştur")]


# ------------------------------------------------------------- adım listesi

def _adimlar() -> List[Adim]:
    K = Klasorler
    return [
        # ---- Hazırlık
        Adim("kurulum", "hazirlik", "Bağımlılıkları kur",
             "Tüm araçların Python paketlerini ve Playwright Chromium tarayıcısını kurar. "
             "İlk kullanımda bir kez çalıştırın.",
             _kurulum, sure="~3 dk"),
        Adim("ortam", "hazirlik", "Ortam kontrolü",
             "Bu bilgisayarda Python paketleri, Chromium, Go ve Docker kurulu mu, tek tek gösterir.",
             _ortam, sure="saniyeler"),
        Adim("saglayici", "hazirlik", "Yapay zekâ sağlayıcılarını dene",
             "Girilen anahtar ve adreslerle Anthropic, Gemini, OpenAI uyumlu servis ve Ollama'ya "
             "bağlanır, kullanılabilir modelleri listeler ve ayarlardaki model adını doğrular.",
             _saglayici, sure="saniyeler"),
        Adim("kesif", "hazirlik", "Site keşfi (link haritası)",
             "Profildeki adresten başlayıp gerçek <a href>/form linklerini izler, URL tahmin "
             "etmez. Kurallar (hariç desenler, sorgu sınırı, tarayıcı modu) Ayarlar > Site "
             "profili'nde. Kesilirse tekrar çalıştırın, kaldığı yerden devam eder.",
             _kesif, lambda a: [K(a).kesif_haritasi], sure="dakikalar-saatler"),
        Adim("kesif_kullan", "hazirlik", "Keşif haritasını kullan",
             "Keşfedilen haritayı bu profilin bundan sonraki tüm adımlarının kaynağı yapar "
             "(yeni profillerde zaten öyledir).",
             _kesif_kullan),

        # ---- Web testi
        Adim("deneme", "web", "Deneme testi",
             "İlk N sayfayı gerçek tarayıcıda test eder (HTTP, güvenlik başlıkları, Türkçe "
             "karakter, erişilebilirlik, mobil, JS hataları, ekran görüntüsü kanıtı).",
             lambda a: [_tester(a, K(a).deneme, "--limit", a["deneme_limit"], "--fresh")],
             lambda a: [K(a).deneme / "report.html"], sure="~2 dk"),
        Adim("tam_test", "web", "Tüm site kanıtlı testi",
             "Haritadaki tüm sayfaları parça parça test eder (tara.bat'ın karşılığı). "
             "Kesilirse tekrar çalıştırın: yapılmış sayfalar atlanır.",
             _tam_test,
             lambda a: [K(a).test / "report.html", K(a).test / "report.xlsx",
                        K(a).test / "summary.txt"], sure="~2 sa, ~8 GB"),
        Adim("hatali_tekrar", "web", "Hatalı sayfaları yeniden test et",
             "Yalnızca hata/zaman aşımı alan sayfaları düşük eşzamanlılıkla tekrar dener.",
             lambda a: [_py(a, "tester_v3_evidence.py", "--source", yol(a["harita"]), "--out-dir",
                            K(a).test, "--retry-errors", "--concurrency", 2,
                            *_site_secenekleri(a))],
             lambda a: [K(a).test / "report.html"]),
        Adim("rapor_yenile", "web", "Test raporunu yeniden üret",
             "Test çalıştırmadan results.jsonl'den report.html/xlsx/summary üretir.",
             lambda a: [_py(a, "tester_v3_evidence.py", "--source", yol(a["harita"]), "--out-dir",
                            K(a).test, "--report-only", *_site_secenekleri(a))],
             lambda a: [K(a).test / "report.html"], sure="saniyeler"),

        # ---- Denetimler
        Adim("belge", "denetim", "Belge denetimi (PDF/Word)",
             "Belge linklerinin erişilebilirliğini ve sızdırılmış yerel yolları denetler.",
             lambda a: [_tester(a, K(a).belge, "--check-docs", "--no-screenshots")],
             lambda a: [K(a).belge / "documents_audit.csv"]),
        Adim("link", "denetim", "Kırık link denetimi",
             "Sayfalardaki tüm iç ve dış bağlantıları kontrol eder.",
             lambda a: [_tester(a, K(a).link, "--check-links", "--no-screenshots")],
             lambda a: [K(a).link / "broken_links.csv"], sure="saatler"),
        Adim("kumeleme", "denetim", "Şablon kümeleme",
             "URL'leri düzen imzasına göre şablonlara indirir (ÖİDB: 17 bin -> ~600), her "
             "şablondan temsilci seçer. Görsel denetim ve yerel model bu temsilcilerle çalışır.",
             lambda a: [_py(a, "cluster_templates.py", "--source", yol(a["harita"]), "--reps",
                            a["temsilci_sayisi"], "--cikti-klasor", K(a).veri)],
             lambda a: [K(a).temsilciler, K(a).kumeler], sure="saniyeler"),
        Adim("gorsel", "denetim", "Görsel/UI kusur denetimi",
             "Şablon temsilcilerinde taşma, kırık görsel, kırpılan metin ve boş render arar; "
             "kusuru kırmızı kutulu ekran görüntüsüyle kanıtlar.",
             lambda a: [_tester(a, K(a).gorsel, "--check-visual", "--no-screenshots", "--fresh",
                                source=str(K(a).temsilciler))],
             lambda a: [K(a).gorsel / "gorsel_rapor.html", K(a).gorsel / "gorsel_denetim.csv"]),

        # ---- Doğrulama
        Adim("rota", "dogrulama", "Kırık sayfa doğrulama (doğrudan erişim)",
             "401/403/404 dönen URL'leri tarayıcıda doğrudan açar: içerik gerçekten gelmiyor mu?",
             lambda a: [_py(a, "verify_routes.py", "--source", K(a).test / "results.jsonl",
                            "--out", K(a).rota_csv,
                            *(["--limit", a["rota_limit"]] if a["rota_limit"] else []))],
             lambda a: [K(a).rota_csv]),
        Adim("tiklama", "dogrulama", "Buton tıklama doğrulama",
             "Sitedeki butonlara gerçekten tıklar: kırık sayfaya mı götürüyor?",
             lambda a: [_py(a, "verify_clicks.py", "--map", yol(a["harita"]), "--limit",
                            a["tiklama_limit"], "--out", K(a).tiklama_csv)],
             lambda a: [K(a).tiklama_csv]),

        # ---- Yapay zekâ görsel denetimi
        Adim("ollama", "ai", "Yerel model incelemesi (Ollama)",
             "Şablon temsilcilerini yerel açık kaynak görüntü modeline sorar. Anahtar ve "
             "ücret yok; Ollama kurulu ve model indirilmiş olmalı.",
             lambda a: [_py(a, "visual_ai_review.py", "--source", K(a).temsilciler, "--model",
                            a["ollama_model"], "--ollama-url", a["ollama_url"], "--out-dir",
                            K(a).gorsel_ai, "--site-adi", a["site_adi"], "--locale",
                            a["locale"])],
             lambda a: [K(a).gorsel_ai / "gorsel_ai_rapor.html"]),
        Adim("ai_tarama", "ai", "1. Kodla piksel taraması",
             "Tüm ekran görüntülerini ölçer (taşma, boş sayfa, eksik eş, aynı görünüm) ve "
             "AI'ya gidecek temsilcileri seçer.",
             lambda a: [_py(a, "tarama.py", "--klasor", K(a).test / "screenshots", "--cikti",
                            K(a).denetim_cikti, cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).denetim_cikti / "tarama.csv", K(a).denetim_cikti / "ornekler.csv",
                        K(a).denetim_cikti / "ozet.txt"]),
        Adim("ai_temsilci", "ai", "2a. Temsilci URL listesi",
             "Seçilen temsilci görüntülerin URL'lerini site haritasından bulur.",
             lambda a: [_py(a, "temsilci_urls.py", "--ornekler",
                            K(a).denetim_cikti / "ornekler.csv", "--harita", yol(a["harita"]),
                            "--cikti", K(a).temsilci_urls, cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).temsilci_urls]),
        Adim("ai_yeniden", "ai", "2b. Kaydırarak yeniden çekim",
             "Temsilci sayfaları sona kadar kaydırarak (lazy görseller, sayaçlar) yeniden çeker.",
             lambda a: [_tester(a, K(a).yeniden, "--kaydir", source=str(K(a).temsilci_urls))],
             lambda a: [K(a).yeniden / "report.html"]),
        Adim("ai_tahmin", "ai", "3a. Maliyet/süre tahmini",
             "API çağırmadan seçili modellerle kaç istek ve ne kadar maliyet çıkacağını gösterir.",
             lambda a: [_analiz(a, "--modeller", a["ai_modeller"], "--tahmin")], sure="saniyeler"),
        Adim("ai_analiz", "ai", "3b. Yapay zekâ analizi",
             "Görüntüleri dilimleyip seçili modellere aynı talimat ve JSON şemasıyla sorar. "
             "Yarıda kalırsa tekrar çalıştırın, kaldığı yerden devam eder.",
             lambda a: [_analiz(a, "--modeller", a["ai_modeller"])],
             lambda a: [K(a).ai_sonuc / "bulgular.csv", K(a).ai_sonuc / "oylama.csv",
                        K(a).ai_sonuc / "ozet.txt"]),
        Adim("ai_hakem", "ai", "3c. Hakem modeli",
             "Modellerin anlaşamadığı veya yüksek önem verdiği dilimleri hakem modele sorar.",
             lambda a: [_analiz(a, "--hakem", a["ai_hakem"],
                                *(["--hakem-ornek", a["ai_hakem_ornek"], "--hakem-grup",
                                   a["ai_hakem_grup"]] if a["ai_hakem_ornek"] else []),
                                *(["--toplu"] if a["ai_toplu"] else []))],
             lambda a: [K(a).ai_sonuc / "oylama.csv"]),
        Adim("ai_isabet", "ai", "4. İsabet ölçümü",
             "Hata türü başına hakem onay oranı ve taşmada piksel ölçümüyle precision/recall.",
             lambda a: [_py(a, "isabet.py", "--cikti", K(a).ai_sonuc, "--ana", a["ai_ana"],
                            "--hakem", a["ai_isabet_hakem"], "--tarama",
                            K(a).denetim_cikti / "tarama.csv", cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).ai_sonuc / "isabet.txt"], sure="saniyeler"),
        Adim("ai_metin", "ai", "5. Metin kodlama denetimi",
             "Görünen metinde Türkçe karakter kaybı (Atat?rk), HTML kodu (&#39;) ve mojibake arar.",
             lambda a: [_py(a, "metin_kontrol.py", "--source", K(a).temsilci_urls, "--cikti",
                            K(a).metin_csv, cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).metin_csv]),
        Adim("ai_rapor", "ai", "6. Görsel denetim son raporu",
             "Kod, metin ve yapay zekâ bulgularını ekran görüntüsü kesitli tek HTML raporda toplar.",
             lambda a: [_py(a, "rapor.py", "--tarama", K(a).denetim_cikti / "tarama.csv",
                            "--ai", K(a).ai_sonuc, "--ana", a["ai_ana"],
                            "--klasor", K(a).yeniden / "screenshots",
                            "--http", K(a).yeniden / "http_hatali.csv",
                            "--metin", K(a).metin_csv, "--cikti", K(a).ai_rapor,
                            "--site-adi", a["site_adi"], cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).ai_rapor / "rapor.html"]),

        # ---- Görsel doğrulama ve düzeltme
        Adim("gd_dogrulama", "duzeltme", "7. Bulguları canlı sitede doğrula",
             "Kod, metin ve yapay zekâ bulgusu olan sayfaları yeniden açıp DOM üzerinde ölçer: "
             "hata hâlâ var mı, çekimden mi kaynaklanmış? Taşmalarda hatayı üreten öğeyi ve kaç "
             "sayfayı etkilediğini çıkarır (kok_neden.csv). Önce yapay zekâ hattı çalışmış olmalı.",
             _dogrulama,
             lambda a: [K(a).dogrulama_cikti / "ozet.txt", K(a).dogrulama_cikti / "sonuc.csv",
                        K(a).dogrulama_cikti / "kok_neden.csv"]),
        Adim("gd_etiket", "duzeltme", "8a. Etiketleme sayfasını oluştur",
             "Kodla ölçülemeyen ve yanlış alarm sayılan bulgularla doğrulananlardan bir örneklemi "
             "tarayıcıda açılan bir sayfada toplar (1 Gerçek, 2 Yanlış, 3 Emin değilim). Bitince "
             "sayfadaki 'CSV indir' ile etiketler.csv kaydedilir.",
             lambda a: [_py(a, "etiketle.py", "olustur", "--dogrulama", K(a).dogrulama, "--klasor",
                            K(a).yeniden / "screenshots", K(a).test / "screenshots", "--ornek",
                            a["etiket_ornek"], "--sonuc", K(a).dogrulama_cikti / "sonuc.csv",
                            "--cikti", K(a).etiket, cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).etiket / "etiketle.html"]),
        Adim("gd_etiket_ozet", "duzeltme", "8b. Etiketleri işle",
             "İndirilen etiketler.csv'den tür başına elle ölçülmüş isabeti ve otomatik doğrulamanın "
             "isabetini hesaplar. Dosya yolu Ayarlar'dan değiştirilebilir (varsayılan: İndirilenler).",
             lambda a: [_py(a, "etiketle.py", "ozet", "--etiketler", etiket_csv(a), "--sonuc",
                            K(a).dogrulama_cikti / "sonuc.csv", "--cikti", K(a).etiket,
                            cwd=yollar.GORSEL_DENETIM)],
             lambda a: [K(a).etiket / "etiket_ozet.txt", K(a).etiket / "sonuc_etiketli.csv"],
             sure="saniyeler"),
        Adim("gd_css", "duzeltme", "9. CSS düzeltme önerisini dene",
             "Önerilen CSS'i canlı sayfalara (yalnız tarayıcı sekmesine) ekleyip yeniden ölçer: kaç "
             "sayfa düzeldi, hangileri kaldı, yeni bozulan var mı. CSS: Ayarlar'da verilen ya da "
             "otomatik düzeltmenin önerisi. Önce 7. adım çalışmış olmalı.",
             _css_deneme, lambda a: [K(a).css_cikti / "css_ozet.txt", K(a).css_cikti / "css_sonuc.csv"]),
        Adim("gd_oto", "duzeltme", "10. Otomatik taşma düzeltme (her site)",
             "Sayfaları ölçer, sayfayı yana kaydıran öğeyi türüne göre sınıflandırır (uzun metin, tablo, "
             "gömülü içerik, sabit genişlik), sitenin kendi sınıflarıyla CSS kuralı üretir, ekleyip "
             "yeniden ölçer ve etkisiz kuralı güçlendirir. Site değişmez. Çıktı: oneri.css ve önce/sonra "
             "görüntüleri.",
             _oto_duzelt,
             lambda a: [K(a).oto / "goruntu" / "karsilastir.html", K(a).oto / "oneri.css",
                        K(a).oto / "ozet.txt"], sure="dakikalar"),

        # ---- Bologna
        Adim("bologna_db", "bologna", "PostgreSQL'i başlat (Docker)",
             "Bologna veritabanını Docker ile arka planda başlatır. Kendi PostgreSQL'iniz "
             "varsa atlayın ve Ayarlar'daki bağlantı adresini girin.",
             lambda a: [Komut(["docker", "compose", "up", "-d", "db"], cwd=yollar.BOLOGNA)]),
        Adim("bologna_test", "bologna", "Birim testleri",
             "Go birim testlerini çalıştırır (parser, istemci, CLI). Go kurulu olmalı.",
             lambda a: [Komut(["go", "test", "./..."], cwd=yollar.BOLOGNA)]),
        Adim("bologna_kesfet", "bologna", "Programları listele",
             "Seçili seviyedeki birim ve programları listeler (veritabanına yazmaz).",
             lambda a: _bologna(a, "discover", "-l", a["bologna_seviye"]), sure="saniyeler"),
        Adim("bologna_program", "bologna", "Tek program tara",
             "Ayarlardaki program numarasını (curSunit) tarar, örn. 1371 Bilgisayar Müh.",
             lambda a: _bologna(a, "scrape", "-p", a["bologna_program"],
                                *_bologna_tarama_secenekleri(a)), sure="~1 dk"),
        Adim("bologna_seviye", "bologna", "Seviye tara",
             "Seçili seviyedeki (önlisans, lisans, yüksek lisans, doktora) tüm programları tarar.",
             lambda a: _bologna(a, "scrape", "-l", a["bologna_seviye"],
                                *_bologna_tarama_secenekleri(a))),
        Adim("bologna_tumu", "bologna", "Tüm siteyi tara",
             "Bologna Bilgi Paketi'nin tamamını PostgreSQL'e yazar.",
             lambda a: _bologna(a, "scrape", "--all", *_bologna_tarama_secenekleri(a)),
             sure="~3,5 sa"),
        Adim("bologna_devam", "bologna", "Kesilen taramayı sürdür",
             "Tüm site taramasını son 24 saatte yazılmış dersleri atlayarak sürdürür.",
             lambda a: _bologna(a, "scrape", "--all", *_bologna_tarama_secenekleri(a),
                                "--fresh-within", "24h")),
        Adim("bologna_istatistik", "bologna", "Veritabanı istatistikleri",
             "Tablolardaki kayıt sayılarını gösterir.",
             lambda a: _bologna(a, "stats"), sure="saniyeler"),

        # ---- Teslim
        Adim("teslim", "teslim", "Teslim paketini oluştur",
             "Tüm rapor ve verileri anlaşılır adlarla TESLIM klasöründe toplar ve bir "
             "içindekiler sayfası (index.html) üretir (toparla.bat'ın karşılığı).",
             _teslim, lambda a: [K(a).teslim / "index.html"], sure="saniyeler"),
    ]


ADIMLAR: List[Adim] = _adimlar()
ADIM: Dict[str, Adim] = {a.id: a for a in ADIMLAR}

# "Tam hat": siteyi baştan sona denetleyen önerilen sıra. AI adımları ayrı bir
# hattır, çünkü API anahtarı ve kota gerektirir.
TAM_HAT = ["tam_test", "belge", "link", "kumeleme", "gorsel", "rota", "tiklama", "teslim"]


def tam_hat(ayar: dict) -> List[str]:
    """Harita henüz yoksa (yeni site) hat keşifle başlar."""
    return (["kesif"] if not harita_url_sayisi(yol(ayar["harita"])) else []) + TAM_HAT
AI_HATTI = ["ai_tarama", "ai_temsilci", "ai_yeniden", "ai_analiz", "ai_hakem", "ai_isabet",
            "ai_metin", "ai_rapor", "gd_dogrulama"]


def grup_adimlari(grup: str) -> List[Adim]:
    return [a for a in ADIMLAR if a.grup == grup]
