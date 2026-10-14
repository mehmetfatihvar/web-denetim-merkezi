"""Web Denetim Merkezi masaüstü arayüzü (Tkinter; Python ile birlikte gelir).

Düzen: solda menü (profil, sayfalar, tema), sağda sayfa içeriği; en altta her zaman görünen
durum şeridi (çalışırken canlılık göstergesi, ilerleme, Durdur) ve isteğe göre açılan ayrıntılar
(çalışma kaydı / hatalar / son çalışma). Görünüm `tema.py`'de.

Kullanım ilkesi: ana sayfada sıradaki aşama (Başlat); adım sayfalarında seçili adım (Çalıştır) ya da
sayfadaki adımlar, önerilenler işaretli bir listeden (Bu sayfadakileri sırayla çalıştır).
"""

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from . import SURUM, adim_raporu, denetim_raporu, tema, yollar
from . import ayarlar as A
from .adimlar import ADIM, GRUPLAR, grup_adimlari
from .calistirici import Calistirici
from .durum import adim_durumlari, kutucuklar, ozet, yol_haritasi
from .izleme import sure_metni

# ------------------------------------------------------------- ayar formları
# (anahtar, etiket, tür, açıklama, seçenekler)
#   tür: metin | sayi | ondalik | evet | secim | yol | dosya | gizli | cok
SITE_ALANLARI = [
    ("Site", [
        ("site_adi", "Site adı", "metin", "Raporların başlığında görünür.", None),
        ("site_url", "Başlangıç adresi", "metin", "Keşfin başladığı adres.", None),
        ("cikti_koku", "Çıktı klasörü", "yol", "Tüm çıktılar bunun altına yazılır.", None),
        ("harita", "Site haritası", "dosya", "Test edilecek sayfaların listesi (JSON).", None),
        ("locale", "Tarayıcı dili", "metin", "Ör. tr-TR, en-US, de-DE", None),
        ("user_agent", "User-Agent", "metin", "Boş bırakılırsa aracın varsayılanı.", None),
    ]),
    ("Keşif kuralları", [
        ("kesif_tarayici", "Tarayıcıyla keşfet (SPA)", "evet",
         "Linkler JavaScript ile üretiliyorsa açın (daha yavaş).", None),
        ("kesif_ssl_yoksay", "Sertifika hatalarını yok say", "evet", "Self-signed SSL için.", None),
        ("kesif_max_sayfa", "En fazla sayfa", "sayi", "", None),
        ("kesif_derinlik", "En fazla derinlik", "sayi", "0 = sınırsız", None),
        ("kesif_isci", "Eşzamanlı istek", "sayi", "", None),
        ("kesif_rps", "Saniyede istek", "ondalik", "Sunucuyu yormamak için. 0 = sınırsız", None),
        ("kesif_haric", "Hariç desenler", "cok",
         "İzlenmeyecek adresler için düzenli ifadeler (boşluk/satırla ayırın), ör. /arama /etiket/", None),
        ("kesif_dahil", "Yalnızca bu desenler", "cok", "Boş = tüm site.", None),
        ("kesif_yoksay_param", "Silinecek sorgu parametreleri", "cok",
         "Sonsuz kombinasyon üreten parametreler (sort, filtre, oturum ...).", None),
        ("kesif_sorgu_limiti", "Yol başına sorgu varyasyonu", "sayi", "0 = sınırsız", None),
        ("kesif_sitemap", "sitemap.xml'i de kullan", "evet", "", None),
        ("kesif_robots", "robots.txt'ye uy", "evet", "", None),
        ("kesif_alt_alanlar", "Alt alan adlarını dahil et", "evet", "", None),
    ]),
    ("Test", [
        ("esz", "Eşzamanlı sekme", "sayi", "4 önerilir; yüksek değer sunucuyu zorlar.", None),
        ("zaman_asimi", "Sayfa zaman aşımı (sn)", "sayi", "", None),
        ("deneme_limit", "Deneme testi sayfa sayısı", "sayi", "", None),
        ("parca", "Tam testte parça boyu", "sayi", "", None),
        ("taze_basla", "Tam testi sıfırdan başlat", "evet",
         "Kapalıysa yapılmış sayfalar atlanır (kaldığı yerden devam).", None),
        ("tablet", "Tablet görüntüsü de al", "evet", "", None),
        ("gorunur", "Tarayıcıyı görünür çalıştır", "evet", "Hata ayıklama için.", None),
        ("temsilci_sayisi", "Şablon başına temsilci", "sayi", "", None),
        ("rota_limit", "Rota doğrulama sınırı", "sayi", "0 = hepsi", None),
        ("tiklama_limit", "Tıklama doğrulama sınırı", "sayi", "", None),
    ]),
    ("Görsel doğrulama ve düzeltme", [
        ("oto_limit", "Otomatik düzeltme: sayfa sayısı", "sayi",
         "Ölçülecek en fazla sayfa (şablonlara yayılarak seçilir).", None),
        ("oto_cihaz", "Otomatik düzeltme: cihaz", "secim", "", ["mobile", "desktop", "ikisi"]),
        ("oto_tur", "Otomatik düzeltme: tur sayısı", "sayi", "En fazla düzeltme turu.", None),
        ("oto_goruntu", "Önce/sonra görüntüsü", "sayi", "Kaç sayfanın görüntüsü alınsın (0 = alma).", None),
        ("css_oneri", "Denenecek CSS dosyası", "dosya",
         "Boş: otomatik düzeltmenin önerisi; o da yoksa hazır oneri.css.", None),
        ("etiket_ornek", "Etiketleme örneklemi", "sayi", "Doğrulananlardan rastgele kaç bulgu.", None),
        ("etiket_csv", "İndirilen etiketler.csv", "dosya", "Boş: İndirilenler klasörü.", None),
    ]),
    ("Yapay zekâ talimatı", [
        ("site_tanimi", "Site tanımı (İngilizce)", "metin",
         "Modele 'You are a UI QA reviewer for ...' diye verilir.", None),
        ("site_dili", "Sitenin dili (İngilizce)", "metin", "Ör. Turkish, English, German", None),
    ]),
    ("Bologna (OİBS)", [
        ("bologna_url", "OİBS Bologna adresi", "metin",
         "OİBS kullanan herhangi bir üniversitenin Bologna adresi; alan adı yeter (ör. obs.ornek.edu.tr). "
         "Her sitenin verisi veritabanında kendi şemasına yazılır (Mersin Üni.: public).", None),
        ("bologna_program", "Program no (curSunit)", "metin", "", None),
        ("bologna_seviye", "Seviye", "secim", "",
         ["onlisans", "lisans", "yukseklisans", "doktora", "onlisans,lisans,yukseklisans,doktora"]),
    ]),
]

GENEL_ALANLARI = [
    ("Sağlayıcılar ve modeller", [
        ("anthropic_key", "Anthropic API anahtarı", "gizli", "", None),
        ("claude_model", "Claude modeli", "metin", "'claude' yazıldığında kullanılan model.", None),
        ("claude_effort", "Claude düşünme düzeyi", "secim", "",
         ["", "low", "medium", "high", "xhigh", "max"]),
        ("gemini_key", "Gemini API anahtarı", "gizli", "", None),
        ("gemini_model", "Gemini modeli", "metin", "'gemini' yazıldığında kullanılan model.", None),
        ("openai_url", "OpenAI uyumlu adres", "secim_yazi",
         "OpenAI, OpenRouter, Groq, LM Studio ... ('openai:<model>')",
         list(A.OPENAI_HAZIR.values())),
        ("openai_key", "OpenAI uyumlu anahtar", "gizli", "Yerel sunucularda boş bırakılabilir.", None),
        ("openai_model", "Varsayılan OpenAI modeli", "metin", "Yalnızca sağlayıcı testinde kontrol edilir.", None),
        ("ollama_url", "Ollama adresi", "metin", "", None),
        ("ollama_model", "Ollama görüntü modeli", "metin", "Ör. minicpm-v, qwen2.5vl:7b", None),
        ("anahtarlari_kaydet", "Anahtarları diske kaydet", "evet",
         "Kapalıysa anahtarlar yalnızca bu oturumda kullanılır.", None),
    ]),
    ("Yapay zekâ analiz hattı", [
        ("ai_modeller", "Tarayan modeller", "metin",
         "Virgülle: claude, gemini, gemini:<model>, openai:<model>, ollama:<model>", None),
        ("ai_hakem", "Hakem modeli", "metin", "Anlaşmazlıkları çözen model, ör. claude", None),
        ("ai_hakem_ornek", "Hakeme örnek sayısı", "sayi", "0 = hepsi", None),
        ("ai_hakem_grup", "Hakem örnek grubu", "secim", "", ["sablon", "tur"]),
        ("ai_toplu", "Claude toplu istek (Batch, %50 ucuz)", "evet", "", None),
        ("ai_limit", "Sayfa sınırı (deneme)", "sayi", "0 = hepsi", None),
        ("ai_dakika_limit", "Dakikada istek sınırı", "sayi", "Ücretsiz kotalar için, 0 = sınırsız", None),
        ("ai_paralel", "Eşzamanlı istek", "sayi", "", None),
        ("ai_ana", "İsabet: ana model", "metin", "sonuclar.jsonl'deki model adı", None),
        ("ai_isabet_hakem", "İsabet: hakem model", "metin", "", None),
    ]),
    ("Bologna veritabanı", [
        ("bologna_mod", "Çalıştırma biçimi", "secim", "docker: Go/PostgreSQL kurmadan", ["docker", "yerel"]),
        ("bologna_db", "PostgreSQL adresi", "metin", "Yerel modda kullanılır.", None),
        ("bologna_havuz", "Havuz ders detayları", "evet", "--pool-details", None),
        ("bologna_yillar", "Plan yılı sayısı", "metin", "1, 3 ya da all", None),
        ("bologna_isci", "Paralel program", "sayi", "", None),
        ("bologna_rps", "Saniyede istek", "ondalik", "2'nin üstü önerilmez.", None),
    ]),
    ("Genel", [
        ("python", "Python yorumlayıcısı", "dosya", "Araçları çalıştıracak Python.", None),
        ("arayuz_gorunumu", "Arayüz görünümü", "secim",
         "sade: hızlı (önerilen). modern: Windows 11 görünümü, ama Windows'ta sayfa geçişleri ve "
         "tema değişimi belirgin yavaştır. Programı yeniden açınca geçerli olur.",
         ["sade", "modern"]),
        ("hata_olursa_devam", "Hata olursa sonraki adımlarla sürdür", "evet",
         "Kapalıyken birden çok adımlı bir çalışmada bir adım başarısız olursa sonrakiler çalışmaz.", None),
        ("ayrintili", "Ayrıntılı kayıt (hata ayıklama)", "evet",
         "Her komutun klasörü, ortamı ve argümanları kayda yazılır; Bologna -v ile çalışır.", None),
    ]),
]

SAYFA_ACIKLAMA = {
    "hazirlik": "Kurulum, yapay zekâ sağlayıcılarının denenmesi ve sitenin sayfalarının keşfi.",
    "web": "Sayfalar gerçek tarayıcıda açılır; her sayfa için ekran görüntüsü kanıtı alınır.",
    "denetim": "Belgeler, kırık bağlantılar ve şablon bazlı görsel/UI kusurları.",
    "dogrulama": "Kırık görünen sayfaların gerçekten kırık olup olmadığı iki yolla teyit edilir.",
    "ai": "Ekran görüntüleri kodla taranır, yapay zekâ modellerine sorulur ve son rapor üretilir.",
    "bologna": "OİBS Bologna Bilgi Paketi'ni tarayıp PostgreSQL'e yazar.",
    "teslim": "Bütün rapor ve verileri anlaşılır adlarla tek klasörde toplar.",
    "duzeltme": "Bulgular canlı sitede doğrulanır, yanlış alarmlar elle ayıklanır, taşma için CSS "
                "düzeltmesi üretilip denenir. Site değişmez; CSS yalnız tarayıcı sekmesine eklenir.",
}
# "Bu sayfadakileri sırayla çalıştır": hepsi işaretli gelir; yalnız şunlar işaretsizdir ve nedeni
# yanında yazar (aynı işi iki kez yapar, ön koşul ister ya da elle yapılacak işi bekler).
ISARETSIZ = {
    "saglayici": "yalnız anahtarları denemek için",
    "kesif_kullan": "hazır haritanın yerine keşif haritasını koyar",
    "ollama": "Ollama kurulu ve model indirilmiş olmalı",
    "gd_etiket_ozet": "etiketlemeyi siz yaptıktan sonra çalıştırın",
    "bologna_test": "geliştirici içindir; Go kurulu olmalı",
    "bologna_program": "deneme içindir; Tüm siteyi tara kapsar",
    "bologna_seviye": "Tüm siteyi tara kapsar",
    "bologna_devam": "yalnız yarıda kalan tarama için",
}
ETIKETLEME_NOTU = ("Etiketleme sizde: zincir 8a ile etiketleme sayfasını oluşturur ama sizi beklemez. "
                   "Sonunda sayfayı açıp bulguları 1/2/3 ile işaretleyin ve 'CSV indir'e basın; sonra ana "
                   "sayfada Başlat ile 8b'yi (etiketleri işle) çalıştırın.")
# Çalışma sırası listedekinden farklı olan sayfalar (9. adım 10.'nun önerisini dener)
SAYFA_SIRASI = {"duzeltme": ["gd_dogrulama", "gd_etiket", "gd_etiket_ozet", "gd_oto", "gd_css"]}
CANLI_KARE = "◐◓◑◒"
SESSIZ_UYARI_SN, SESSIZ_CIDDI_SN = 120, 600
DURUM_YAZI = {"baslangic": "● Çalışıyor", "basarili": "✔ Başarılı", "hatali": "✖ Başarısız",
              "durdu": "■ Durduruldu"}


def ac(yol):
    """Dosya/klasörü işletim sisteminin varsayılan programıyla aç."""
    yol = str(yol)
    try:
        if os.name == "nt":
            os.startfile(yol)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", yol])
        else:
            subprocess.Popen(["xdg-open", yol], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        messagebox.showerror("Açılamadı", f"{yol}\n\n{e}")


def _kisa_yol(p: Path) -> str:
    """Repo içindeki yolları göreli göster (ör. tools/test_output/report.html)."""
    try:
        return Path(p).resolve().relative_to(yollar.REPO).as_posix()
    except ValueError:
        return str(p)


def _kutu_sar(etiket, genislik):
    """Özet kutusunun alt yazısını kutu genişliğinde kaydırır (_sar'ın 200 px alt sınırı yok)."""
    genislik = max(int(genislik), 60)
    if abs(int(str(etiket.cget("wraplength") or 0)) - genislik) >= 8:
        etiket.configure(wraplength=genislik)


def _sar(etiketler, genislik):
    """Etiketlerin satır kaydırma genişliğini ayarlar. Yalnızca belirgin değişimde yazar:
    her piksel değişiminde yazmak yeniden yerleşime, o da yeni <Configure> olayına yol açar
    ve pencere boyutlandırılırken arayüzü kasar."""
    genislik = max(int(genislik), 200)
    for e in etiketler:
        if abs(int(str(e.cget("wraplength") or 0)) - genislik) >= 8:
            e.configure(wraplength=genislik)


class _CizimiDondur:
    """Windows'ta bir alanın ekrana çizimini geçici olarak durdurur, sonra tek seferde gösterir.

    Tk Windows'ta her öğeyi ayrı bir pencere olarak çizer; sayfa değişirken ya da kutular yeniden
    kurulurken öğeler tek tek görünür ve düzen "yavaş yavaş genişliyor" gibi görünür. Bu sırada
    WM_SETREDRAW ile çizim kapatılır, iş bitince alan bir kerede yeniden çizilir.
    Başka sistemlerde hiçbir şey yapmaz.
    """

    derinlik = {}                       # iç içe kullanımda yalnız en dıştaki açar/kapatır

    def __init__(self, w):
        self.w = w
        self.hwnd = None

    def __enter__(self):
        anahtar = str(self.w)
        _CizimiDondur.derinlik[anahtar] = _CizimiDondur.derinlik.get(anahtar, 0) + 1
        if _CizimiDondur.derinlik[anahtar] == 1 and os.name == "nt":
            try:
                import ctypes
                self.user32 = ctypes.windll.user32
                self.hwnd = self.w.winfo_id()
                self.user32.SendMessageW(self.hwnd, 0x000B, 0, 0)        # WM_SETREDRAW = FALSE
            except Exception:
                self.hwnd = None
        return self

    def __exit__(self, *_):
        _CizimiDondur.derinlik[str(self.w)] -= 1
        if self.hwnd is None:
            return False
        try:
            self.w.update_idletasks()       # yerleşim ve çizim hesapları ekran kapalıyken biter
        finally:
            try:
                self.user32.SendMessageW(self.hwnd, 0x000B, 1, 0)    # WM_SETREDRAW = TRUE
                # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME
                self.user32.RedrawWindow(self.hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100 | 0x0400)
            except Exception:
                pass
        return False


class KaydirmaliCerceve(ttk.Frame):
    """İçeriği dikey kaydırılabilen çerçeve."""
    hepsi = []

    def __init__(self, ust, **kw):
        super().__init__(ust, **kw)
        self.tuval = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        cubuk = ttk.Scrollbar(self, orient="vertical", command=self.tuval.yview)
        self.ic = ttk.Frame(self.tuval)
        self.ic.bind("<Configure>", lambda e: self.tuval.configure(scrollregion=(0, 0, e.width, e.height)))
        pencere = self.tuval.create_window((0, 0), window=self.ic, anchor="nw")
        self.tuval.bind("<Configure>", lambda e: self.tuval.itemconfigure(pencere, width=e.width))
        self.tuval.configure(yscrollcommand=cubuk.set)
        self.tuval.pack(side="left", fill="both", expand=True)
        cubuk.pack(side="right", fill="y")
        for olay in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.ic.bind_all(olay, self._tekerlek, add="+")
        KaydirmaliCerceve.hepsi.append(self)

    def _tekerlek(self, e):
        w = e.widget
        while w is not None and w is not self:
            w = getattr(w, "master", None)
        if w is None:
            return
        adim = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
        self.tuval.yview_scroll(adim, "units")

    def renk(self, bg):
        self.tuval.configure(background=bg)


class Uygulama:
    def __init__(self, kok: tk.Tk, ayar: dict):
        self.kok = kok
        self.ayar = ayar
        self.kuyruk = queue.Queue()
        self.calistirici = Calistirici(self._yaz_kuyruga, self._olay_kuyruga)
        self.is_parcacigi = None
        self.calisma_bas = None
        self.son_ilerleme = None
        self.sorun_sayisi = 0
        self.adim_sayisi = 0
        self.son_hareket = None          # araçtan son çıktı/olay zamanı (canlılık göstergesi)
        self.canli_kare = 0
        self.calisan_grup = None
        self.ayrinti_acik = False
        self.calistir_dugmeleri = []     # çalışma sürerken kapatılan düğmeler
        self.adim_durumu = {}            # bu oturumda: adım id -> (durum, metin)
        self.listeler = {}               # grup -> Treeview
        self.ayrinti = {}                # grup -> ayrıntı paneli parçaları
        self.alanlar = {}                # ayar anahtarı -> (tür, değişken/widget)
        self.sayfalar = {}               # sayfa adı -> çerçeve
        self.menu_ogeleri = {}           # sayfa adı -> etiket
        self.etkin_sayfa = None

        kok.withdraw()                   # düzen oturana kadar gizli: öğeler tek tek belirmesin
        kok.title(f"Web Denetim Merkezi {SURUM}")
        kok.geometry("1320x900")
        kok.minsize(1040, 700)
        self.hizli = self.ayar.get("arayuz_gorunumu") != "modern"
        self.p = tema.uygula(kok, self.ayar.get("tema", "light"), self.hizli)
        self.yazi = tema.yazi_ailesi()
        self._iskelet()
        self._profil_yukle_arayuze()
        self._sayfa_ac("ana")
        self._tema_renkleri()
        kok.update_idletasks()
        kok.deiconify()
        self.ortam_sorunlari = []
        threading.Thread(target=self._ortami_denetle, daemon=True).start()
        kok.after(100, self._kuyrugu_bosalt)
        kok.protocol("WM_DELETE_WINDOW", self._kapat)
        kok.bind("<F5>", lambda _: self._durumu_yenile())

    # ================================================================ iskelet
    def _iskelet(self):
        kap = ttk.Frame(self.kok)
        kap.pack(fill="both", expand=True)
        self._yan_menu(kap)
        sag = ttk.Frame(kap)
        sag.pack(side="left", fill="both", expand=True)
        self._ust_cubuk(sag)
        self._durum_seridi(sag)          # en altta, her zaman görünür
        bol = ttk.PanedWindow(sag, orient="vertical")
        bol.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        self.bolme = bol
        self.icerik = ttk.Frame(bol)
        bol.add(self.icerik, weight=5)
        self.alt = ttk.Frame(bol)        # ayrıntılar: kayıt, hatalar, son çalışma (açılır/kapanır)
        self._alt_panel(self.alt)

        self.sayfalar["ana"] = self._ana_sayfa()
        for grup, _ in GRUPLAR:
            self.sayfalar[grup] = self._grup_sayfasi(grup)
        self.sayfalar["raporlar"] = self._raporlar_sayfasi()
        self.sayfalar["ayarlar"] = self._ayarlar_sayfasi()
        # Bütün sayfalar aynı yerde üst üste durur ve bir kez yerleşir; sayfa geçişinde yalnızca
        # öndeki değişir. (Her geçişte gizle/göster yapmak Windows'ta düzenin parça parça
        # kurulmasına ve geçişin yavaş görünmesine yol açıyordu.)
        for sayfa in self.sayfalar.values():
            sayfa.place(x=0, y=0, relwidth=1, relheight=1)

    def _yan_menu(self, ust):
        # Sol menü klasik Tk öğeleriyle: arka plan ve seçili satır rengi her temada tam denetlenir
        y = tk.Frame(ust, width=236)
        y.pack(side="left", fill="y")
        y.pack_propagate(False)
        tk.Frame(ust, width=1).pack(side="left", fill="y")   # ayırıcı çizgi
        self.yan = y
        self.yan_ayirici = ust.winfo_children()[-1]
        self.yan_etiketler = []      # (etiket, tür) — tema değişince yeniden boyanır

        def etiket(metin, tur, **pack):
            e = tk.Label(y, text=metin, anchor="w", padx=0)
            e.pack(fill="x", **pack)
            self.yan_etiketler.append((e, tur))
            return e

        etiket("Web Denetim\nMerkezi", "baslik", padx=18, pady=(20, 0))
        etiket("Web sitesi test ve denetim", "soluk", padx=18)
        etiket("SİTE PROFİLİ", "kucuk", padx=18, pady=(22, 4))
        self.profil_secim = ttk.Combobox(y, state="readonly", values=A.profiller())
        self.profil_secim.pack(fill="x", padx=14)
        self.profil_secim.bind("<<ComboboxSelected>>", self._profil_degisti)
        ttk.Button(y, text="+  Yeni site ekle", command=self._yeni_site).pack(fill="x", padx=14, pady=(6, 0))
        etiket("MENÜ", "kucuk", padx=18, pady=(22, 4))
        ogeler = [("ana", "Ana sayfa")] + list(GRUPLAR) + [("raporlar", "Raporlar ve özet"),
                                                          ("ayarlar", "Ayarlar")]
        self.menu_basliklari = dict(ogeler)
        for ad, baslik in ogeler:
            e = tk.Label(y, text=baslik, anchor="w", padx=14, pady=7, cursor="hand2")
            e.pack(fill="x", padx=8, pady=1)
            e.bind("<Button-1>", lambda _, a=ad: self._sayfa_ac(a))
            e.bind("<Enter>", lambda _, a=ad: self._menu_uzerinde(a, True))
            e.bind("<Leave>", lambda _, a=ad: self._menu_uzerinde(a, False))
            self.menu_ogeleri[ad] = e
            if ad in ("ana", "teslim"):
                cizgi = tk.Frame(y, height=1)
                cizgi.pack(fill="x", padx=16, pady=6)
                self.yan_etiketler.append((cizgi, "cizgi"))

        self.tema_var = tk.BooleanVar(value=self.ayar.get("tema") == "dark")
        self.tema_dugmesi = tk.Label(y, anchor="w", padx=14, pady=7, cursor="hand2")
        self.tema_dugmesi.pack(side="bottom", fill="x", padx=8, pady=(0, 14))
        self.tema_dugmesi.bind("<Button-1>", lambda _: (self.tema_var.set(not self.tema_var.get()),
                                                        self._tema_degistir()))
        self.yan_etiketler.append((self.tema_dugmesi, "menu"))
        surum = tk.Label(y, text=f"Sürüm {SURUM}" + (" · modern görünüm" if tema.sv_ttk_var() and not self.hizli else ""),
                         anchor="w")
        surum.pack(side="bottom", fill="x", padx=22)
        self.yan_etiketler.append((surum, "kucuk"))

    def _yan_boya(self):
        p, aile = self.p, self.yazi
        self.yan.configure(background=p["yan"])
        self.yan_ayirici.configure(background=p["kenar"])
        for e, tur in self.yan_etiketler:
            if tur == "cizgi":
                e.configure(background=p["kenar"])
                continue
            e.configure(background=p["yan"], foreground=p["soluk"] if tur in ("soluk", "kucuk") else p["metin"],
                        font={"baslik": (aile, 15, "bold"), "kucuk": (aile, 8, "bold")}.get(tur, (aile, 10)))
        self.tema_dugmesi.configure(text="☀  Açık temaya geç" if self.tema_var.get() else "☾  Karanlık temaya geç")
        for ad in self.menu_ogeleri:
            self._menu_boya(ad)

    def _menu_boya(self, ad, uzerinde=False):
        p = self.p
        secili = ad == self.etkin_sayfa
        calisan = ad == self.calisan_grup
        self.menu_ogeleri[ad].configure(
            text=self.menu_basliklari[ad] + (f"   {CANLI_KARE[self.canli_kare % 4]}" if calisan else ""))
        self.menu_ogeleri[ad].configure(
            background=p["secili"] if secili else (p["kenar"] if uzerinde else p["yan"]),
            foreground=p["metin"], font=(self.yazi, 10, "bold" if secili else "normal"))

    def _ust_cubuk(self, ust):
        c = ttk.Frame(ust, padding=(16, 14, 16, 10))
        c.pack(fill="x")
        self.sayfa_basligi = ttk.Label(c, text="", style="Baslik.TLabel")
        self.sayfa_basligi.pack(anchor="w")
        self.sayfa_alt = ttk.Label(c, text="", style="Soluk.TLabel", wraplength=520, justify="left")
        self.sayfa_alt.pack(anchor="w", fill="x")
        c.bind("<Configure>", lambda e: _sar([self.sayfa_alt], e.width - 40))

    def _bolmeyi_ayarla(self, oran=0.55):
        """Ayrıntılar açıkken içerik ile ayrıntılar arasındaki bölme."""
        self.kok.update_idletasks()
        h = self.bolme.winfo_height()
        if h > 200 and self.ayrinti_acik:
            self.bolme.sashpos(0, int(h * oran))

    def _ayrintilar(self, acik=None, sekme=None):
        """Kayıt / hatalar / son çalışma panelini aç-kapat. Boştayken kapalıdır: ekranı içerik kullanır."""
        acik = (not self.ayrinti_acik) if acik is None else acik
        if acik != self.ayrinti_acik:
            self.ayrinti_acik = acik
            if acik:
                self.bolme.add(self.alt, weight=4)
                self.kok.after(50, self._bolmeyi_ayarla)
            else:
                self.bolme.forget(self.alt)
        if acik and sekme is not None:
            self.alt_defter.select(sekme)
        self.ayrinti_dugmesi.configure(text="Ayrıntıları gizle  ▾" if acik else "Ayrıntılar  ▴")

    def _sayfa_ac(self, ad):
        with _CizimiDondur(self.icerik):
            self._sayfa_degistir(ad)

    def _sayfa_degistir(self, ad):
        onceki, self.etkin_sayfa = self.etkin_sayfa, ad
        # Arkadaki sayfalar o anki boyutlarında sabitlenir: pencere boyutlanırken yeniden
        # yerleşmezler. Öne gelen sayfa alanı kaplar (boyut değişmediyse hiç yeniden yerleşmez).
        for adi, sayfa in self.sayfalar.items():
            if adi != ad and float(sayfa.place_info().get("relwidth") or 0) > 0:
                sayfa.place_configure(relwidth=0, relheight=0, width=max(sayfa.winfo_width(), 1),
                                      height=max(sayfa.winfo_height(), 1))
        self.sayfalar[ad].place_configure(relwidth=1, relheight=1, width=0, height=0)
        self.sayfalar[ad].tkraise()
        if onceki and onceki != ad:           # klavye odağı arkada kalan sayfada kalmasın
            try:
                odak = self.kok.focus_get()
            except (KeyError, tk.TclError):   # tkinter: açık açılır listede focus_get hata verebilir
                odak = None
            if odak is not None and str(odak).startswith(str(self.sayfalar[onceki])):
                self.sayfalar[ad].focus_set()
        for a in self.menu_ogeleri:
            self._menu_boya(a)
        basliklar = dict(GRUPLAR)
        basliklar.update(ana="Ana sayfa", raporlar="Raporlar ve özet", ayarlar="Ayarlar")
        self.sayfa_basligi.configure(text=basliklar[ad])
        alt = {"ana": f'{self.ayar["site_adi"]}  ·  {self.ayar["site_url"]}',
               "raporlar": "Çıktılardan özet sayılar ve raporlar.",
               "ayarlar": "Site profili seçili siteye, diğer ayarlar tüm sitelere uygulanır."}
        self.sayfa_alt.configure(text=alt.get(ad, SAYFA_ACIKLAMA.get(ad, "")))
        if ad in self.listeler:
            self._ayrinti_goster(ad)
        if ad in ("ana", "raporlar"):
            self._ana_sayfayi_doldur()
            self._durumu_yenile()

    def _menu_uzerinde(self, ad, uzerinde):
        self._menu_boya(ad, uzerinde)

    # ================================================================ ana sayfa
    def _ortami_denetle(self):
        from .ortam import kontrol, sorunlar
        self.kuyruk.put(("ortam", sorunlar(kontrol(self.ayar["python"]))))

    def _ana_sayfa(self):
        kc = KaydirmaliCerceve(self.icerik)
        f = kc.ic
        self.uyari_karti = ttk.Frame(f, style="Card.TFrame", padding=(16, 12))
        # önce düğmeler: metin uzunsa düğmeler değil metin sarılır
        ttk.Button(self.uyari_karti, text="Ortam kontrolü", command=lambda: self._baslat(["ortam"])
                   ).pack(side="right", anchor="n")
        ttk.Button(self.uyari_karti, text="▶  Bağımlılıkları kur", style="Accent.TButton",
                   command=lambda: self._baslat(["kurulum", "ortam"])).pack(side="right", anchor="n", padx=6)
        self.uyari_metni = ttk.Label(self.uyari_karti, text="", style="Uyari.TLabel", justify="left",
                                     wraplength=600)
        self.uyari_metni.pack(side="left", anchor="w", fill="x", expand=True)
        self.uyari_metni.bind("<Configure>", lambda e: _sar([self.uyari_metni], e.width - 10))

        # Sıradaki aşama: ana sayfanın tek ana eylemi
        self.siradaki = ttk.Frame(f, style="Card.TFrame")
        self.siradaki.pack(fill="x", pady=(0, 12))
        self.siradaki_serit = tk.Frame(self.siradaki, width=5)
        self.siradaki_serit.pack(side="left", fill="y")
        ic = ttk.Frame(self.siradaki, padding=(16, 14))
        ic.pack(side="left", fill="both", expand=True)
        dugmeler = ttk.Frame(ic)
        dugmeler.pack(side="right", anchor="center", padx=(12, 0))
        self.siradaki_dugme = ttk.Button(dugmeler, text="▶  Başlat", style="Buyuk.Accent.TButton")
        self.siradaki_dugme.pack(anchor="e")
        self.kalanlar_dugme = ttk.Button(dugmeler, text="Kalanları da sırayla çalıştır")
        self.kalanlar_dugme.pack(anchor="e", pady=(6, 0))
        self.calistir_dugmeleri += [self.siradaki_dugme, self.kalanlar_dugme]
        self.siradaki_ust = ttk.Label(ic, text="SIRADAKİ ADIM", style="Soluk.TLabel")
        self.siradaki_ust.pack(anchor="w")
        self.siradaki_baslik = ttk.Label(ic, text="", style="Buyuk.TLabel")
        self.siradaki_baslik.pack(anchor="w")
        self.siradaki_aciklama = ttk.Label(ic, text="", style="Soluk.TLabel", justify="left")
        self.siradaki_aciklama.pack(anchor="w", fill="x")
        ic.bind("<Configure>", lambda e: _sar([self.siradaki_aciklama], e.width - 300))

        self.kutu_cercevesi = ttk.Frame(f)
        self.kutu_cercevesi.pack(fill="x", pady=(0, 12))

        govde = ttk.Frame(f)
        govde.pack(fill="both", expand=True)
        govde.columnconfigure(0, weight=3)
        govde.columnconfigure(1, weight=2)

        yh = ttk.Frame(govde, style="Card.TFrame", padding=16)
        yh.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(yh, text="Yol haritası", style="AltBaslik.TLabel").pack(anchor="w")
        ttk.Label(yh, text="Bütün aşamalar ve durumları. Bir aşamaya tıklayınca adımları açılır.",
                  style="Soluk.TLabel").pack(anchor="w", pady=(0, 8))
        self.yol_cercevesi = ttk.Frame(yh)
        self.yol_cercevesi.pack(fill="x")

        rk = ttk.Frame(govde, style="Card.TFrame", padding=16)
        rk.grid(row=0, column=1, sticky="new")
        ttk.Label(rk, text="Raporlar", style="AltBaslik.TLabel").pack(anchor="w")
        self.rapor_aciklama = ttk.Label(rk, text="", style="Soluk.TLabel", wraplength=300, justify="left")
        self.rapor_aciklama.pack(anchor="w", pady=(0, 8))
        self.rapor_cercevesi = ttk.Frame(rk)
        self.rapor_cercevesi.pack(fill="x")
        return kc

    def _ortam_uyarisi(self, sorunlar):
        self.ortam_sorunlari = sorunlar
        if sorunlar:
            self.uyari_metni.configure(text="Bu bilgisayarda kurulum eksik:\n" +
                                       "\n".join(f"•  {s}" for s in sorunlar))
            self.uyari_karti.pack(fill="x", pady=(0, 12), before=self.siradaki)
            self._yaz("⚠ Kurulum eksik: " + "; ".join(sorunlar) +
                      ". Ana sayfadaki 'Bağımlılıkları kur' düğmesini kullanın.\n")
        else:
            self.uyari_karti.pack_forget()

    def _rapor_yollari(self):
        k = lambda: A.Klasorler(self.ayar)  # noqa: E731
        return [
            ("Kanıtlı test raporu", lambda: k().test / "report.html"),
            ("Deneme testi raporu", lambda: k().deneme / "report.html"),
            ("Kırık link raporu", lambda: denetim_raporu.link_raporu_yolu(self.ayar)),
            ("Kırık belge raporu", lambda: denetim_raporu.belge_raporu_yolu(self.ayar)),
            ("Görsel kusur raporu", lambda: k().gorsel / "gorsel_rapor.html"),
            ("Yapay zekâ son raporu", lambda: k().ai_rapor / "rapor.html"),
            ("Doğrulama özeti", lambda: k().dogrulama_cikti / "ozet.txt"),
            ("Etiketleme sayfası (8a)", lambda: k().etiket / "etiketle.html"),
            ("Taşma düzeltme (önce/sonra)", lambda: k().oto / "goruntu" / "karsilastir.html"),
            ("Teslim paketi", lambda: k().teslim / "index.html"),
            ("Adım raporları (her çalışma)", lambda: k().adim_raporlari / "index.html"),
            ("Çıktı klasörü", lambda: k().kok),
        ]

    def _ana_sayfayi_doldur(self, zorla=False):
        """Sıradaki aşama, kutucuklar ve yol haritası son durum verisinden kurulur; veri
        değişmediyse dokunulmaz (raporlar yine de güncellenir: yeni dosya üretilmiş olabilir)."""
        veri = getattr(self, "_son_durum", None)
        if veri is None:
            return
        imza = (veri["kutular"], veri["yol"])
        if zorla or imza != getattr(self, "_ana_imza", None):
            self._ana_imza = imza
            with _CizimiDondur(self.icerik):
                self._ana_sayfayi_kur(veri)
        self._raporlari_kur()

    def _ana_sayfayi_kur(self, veri):
        for w in self.kutu_cercevesi.winfo_children():
            w.destroy()
        for i, (baslik, deger, alt, vurgu) in enumerate(veri["kutular"]):
            kutu = ttk.Frame(self.kutu_cercevesi, style="Card.TFrame", padding=(16, 12))
            kutu.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            self.kutu_cercevesi.columnconfigure(i, weight=1, uniform="kutu")
            baslik_etiket = ttk.Label(kutu, text=baslik, style="Soluk.TLabel", justify="left")
            baslik_etiket.pack(anchor="w")
            stil = {"vurgu": "SayiVurgu.TLabel", "hata": "SayiHata.TLabel"}.get(vurgu, "Sayi.TLabel")
            ttk.Label(kutu, text=deger, style=stil).pack(anchor="w")
            alt_etiket = ttk.Label(kutu, text=alt, style="Soluk.TLabel", justify="left")
            alt_etiket.pack(anchor="w")
            kutu.bind("<Configure>", lambda e, ls=(baslik_etiket, alt_etiket):   # dar kutuda kesilmesin
                      [_kutu_sar(l, e.width - 32) for l in ls])
            for l in (baslik_etiket, alt_etiket):    # kutu genişliğini yazı değil ızgara belirlesin
                l.configure(wraplength=60)

        yol = veri["yol"]
        onerilen = next((i for i, a in enumerate(yol) if not a[2]), None)
        self._siradaki_kur(yol, onerilen)

        for w in self.yol_cercevesi.winfo_children():
            w.destroy()
        for i, (baslik, aciklama, tamam, ayrinti, ids) in enumerate(yol):
            satir = ttk.Frame(self.yol_cercevesi, padding=(0, 5), cursor="hand2")
            satir.pack(fill="x")
            satir.columnconfigure(1, weight=1)
            isaret = "✔" if tamam else ("▶" if i == onerilen else "○")
            ogeler = [ttk.Label(satir, text=isaret, width=2, font=(self.yazi, 13, "bold"),
                                foreground=self.p["basari"] if tamam else (self.p["vurgu"] if i == onerilen
                                                                           else self.p["soluk"]))]
            ogeler[0].grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8))
            ogeler.append(ttk.Label(satir, text=f"{i + 1}. {baslik}" + (f"   ·  {ayrinti}" if ayrinti else ""),
                                    style="Vurgu.TLabel" if i == onerilen else "Kalin.TLabel"))
            ogeler[-1].grid(row=0, column=1, sticky="w")
            ogeler.append(ttk.Label(satir, text=aciklama, style="Soluk.TLabel"))
            ogeler[-1].grid(row=1, column=1, sticky="w")
            ogeler.append(ttk.Label(satir, text="›", style="Soluk.TLabel", font=(self.yazi, 14)))
            ogeler[-1].grid(row=0, column=2, rowspan=2, sticky="e")
            grup = ADIM[ids[0]].grup
            for w in [satir] + ogeler:
                w.bind("<Button-1>", lambda _, g=grup, a=ids[0]: self._adima_git(g, a))

    def _siradaki_kur(self, yol, onerilen):
        """Ana sayfanın tepesindeki tek ana eylem: sıradaki aşama ve Başlat."""
        if onerilen is None:
            self.siradaki_ust.configure(text="HEPSİ TAMAM")
            self.siradaki_baslik.configure(text="Bütün aşamalar tamamlandı")
            self.siradaki_aciklama.configure(text="Raporlar sağdaki listede. Teslim paketini yeniden "
                                                  "oluşturmak ya da bir adımı tekrar çalıştırmak için ilgili "
                                                  "sayfayı açın.")
            self.siradaki_dugme.configure(text="Teslim paketini aç",
                                          command=lambda: self._yol_ac(A.Klasorler(self.ayar).teslim / "index.html"))
            self.kalanlar_dugme.pack_forget()
            return
        baslik, aciklama, _, ayrinti, ids = yol[onerilen]
        kalan = self._kalan_adimlar(yol, onerilen)
        self.siradaki_ust.configure(text=f"SIRADAKİ ADIM  ·  {onerilen + 1}/{len(yol)}")
        self.siradaki_baslik.configure(text=baslik + (f"   ·  {ayrinti}" if ayrinti else ""))
        adlar = ", ".join(ADIM[a].ad for a in ids)
        self.siradaki_aciklama.configure(text=f"{aciklama}\nÇalışacak: {adlar}")
        self.siradaki_dugme.configure(text="▶  Başlat", command=lambda: self._hat(ids, baslik))
        if len(kalan) > len(ids):
            self.kalanlar_dugme.configure(command=lambda: self._hat(
                kalan, "Kalan aşamalar", ETIKETLEME_NOTU if "gd_etiket" in kalan else ""))
            self.kalanlar_dugme.pack(anchor="e", pady=(6, 0))
        else:
            self.kalanlar_dugme.pack_forget()

    @staticmethod
    def _kalan_adimlar(yol, onerilen):
        """Sıradaki aşamadan sona kalan adımlar. 8b atlanır: sizin etiketlemenizi bekler."""
        sira = []
        for baslik, aciklama, tamam, ayrinti, ids in yol[onerilen:]:
            if tamam:
                continue
            sira += [a for a in ids if a not in sira and a != "gd_etiket_ozet"]
        return sira

    def _adima_git(self, grup, adim_id):
        self._sayfa_ac(grup)
        t = self.listeler[grup]
        t.selection_set(adim_id)
        t.focus(adim_id)
        t.see(adim_id)
        self._ayrinti_goster(grup)

    def _raporlari_kur(self):
        """Ana sayfada yalnız üretilmiş raporlar görünür (soluk, basılamaz düğme yok)."""
        var = [(ad, fn) for ad, fn in self._rapor_yollari() if fn().exists()]
        imza = tuple(ad for ad, _ in var)
        if imza == getattr(self, "_rapor_imza", None):
            return
        self._rapor_imza = imza
        for w in self.rapor_cercevesi.winfo_children():
            w.destroy()
        for ad, fn in var:
            ttk.Button(self.rapor_cercevesi, text=ad, command=lambda fn=fn: self._yol_ac(fn())
                       ).pack(fill="x", pady=2)
        self.rapor_aciklama.configure(text="Açmak için tıklayın." if var else
                                      "Henüz rapor yok. Adımlar çalıştıkça burada görünür.")

    # ================================================================ adım sayfaları
    def _grup_sayfasi(self, grup):
        f = ttk.Frame(self.icerik)
        # uniform: liste ve kart hep 3:2 bölünür; seçilen adımın metni kartın genişliğini oynatmaz
        f.columnconfigure(0, weight=3, uniform="adim")
        f.columnconfigure(1, weight=2, uniform="adim")
        f.rowconfigure(0, weight=1)

        sol = ttk.Frame(f)
        sol.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        t = ttk.Treeview(sol, columns=("ad", "sure", "durum"), show="headings", selectmode="browse")
        for kol, baslik, gen, uzar in (("ad", "Adım", 320, True), ("sure", "Tahmini süre", 120, False),
                                       ("durum", "Durum", 220, False)):
            t.heading(kol, text=baslik, anchor="w")
            t.column(kol, width=gen, stretch=uzar, anchor="w")
        for adim in grup_adimlari(grup):
            t.insert("", "end", iid=adim.id, values=(adim.ad, adim.sure or "", ""))
        kc = ttk.Scrollbar(sol, command=t.yview)
        t.configure(yscrollcommand=kc.set)
        if len(grup_adimlari(grup)) > 1:
            alt = ttk.Frame(sol)
            alt.pack(side="bottom", fill="x", pady=(8, 0))
            hepsi = ttk.Button(alt, text="▶▶  Bu sayfadakileri sırayla çalıştır…",
                               command=lambda g=grup: self._sayfayi_calistir(g))
            hepsi.pack(side="left")
            self.calistir_dugmeleri.append(hepsi)
        t.pack(side="left", fill="both", expand=True)
        kc.pack(side="right", fill="y")
        t.bind("<<TreeviewSelect>>", lambda _, g=grup: self._ayrinti_goster(g))
        self.listeler[grup] = t

        kart = ttk.Frame(f, style="Card.TFrame", padding=18)
        kart.grid(row=0, column=1, sticky="nsew")
        baslik = ttk.Label(kart, text="", style="AltBaslik.TLabel", wraplength=380, justify="left")
        baslik.pack(anchor="w")
        durum = ttk.Label(kart, text="", style="Soluk.TLabel")
        durum.pack(anchor="w", pady=(2, 8))
        aciklama = ttk.Label(kart, text="", wraplength=380, justify="left")
        aciklama.pack(anchor="w", fill="x")
        ttk.Label(kart, text="Çıktılar", style="Kalin.TLabel").pack(anchor="w", pady=(14, 2))
        ciktilar = ttk.Label(kart, text="", style="Soluk.TLabel", wraplength=380, justify="left")
        ciktilar.pack(anchor="w", fill="x")
        dugmeler = ttk.Frame(kart)
        dugmeler.pack(anchor="w", pady=(16, 0), fill="x")
        calistir = ttk.Button(dugmeler, text="▶  Çalıştır", style="Accent.TButton")
        calistir.pack(side="left")
        self.calistir_dugmeleri.append(calistir)
        cikti = ttk.Button(dugmeler, text="Sonucu aç")
        cikti.pack(side="left", padx=6)
        diger = ttk.Button(dugmeler, text="Diğer  ▾")
        diger.pack(side="left")
        kart.bind("<Configure>", lambda e, ls=(baslik, aciklama, ciktilar): _sar(ls, e.width - 40))
        self.ayrinti[grup] = dict(baslik=baslik, durum=durum, aciklama=aciklama, ciktilar=ciktilar,
                                  calistir=calistir, cikti=cikti, diger=diger)
        ilk = grup_adimlari(grup)[0].id
        t.selection_set(ilk)
        t.focus(ilk)
        return f

    def _ayrinti_goster(self, grup):
        t = self.listeler[grup]
        adim_id = t.focus() or (t.selection() or [None])[0]
        if not adim_id:
            return
        adim = ADIM[adim_id]
        a = self.ayrinti[grup]
        a["baslik"].configure(text=adim.ad)
        durum_metni = self._durum_metni(adim_id)
        a["durum"].configure(text=(f"Tahmini süre: {adim.sure}   ·   " if adim.sure else "") + durum_metni)
        a["aciklama"].configure(text=adim.aciklama)
        try:
            yollar_ = adim.ciktilar(self.ayar)
        except Exception:
            yollar_ = []
        if yollar_:
            a["ciktilar"].configure(text="\n".join(
                ("✔\u00a0" if p.exists() else "○\u00a0") + _kisa_yol(p) for p in yollar_))
        else:
            a["ciktilar"].configure(text="Bu adım dosya üretmez; sonuç adım raporunda ve çalışma kaydında görünür.")
        var = [p for p in yollar_ if p.exists()]
        calisiyor = self.calistirici.calisiyor or bool(self.is_parcacigi and self.is_parcacigi.is_alive())
        a["calistir"].configure(command=lambda: self._baslat([adim_id]),
                                state="disabled" if calisiyor else "normal")
        a["cikti"].configure(state="normal" if var else "disabled", command=lambda: self._cikti_ac(adim_id))
        a["diger"].configure(command=lambda: self._diger_menu(a["diger"], adim_id, yollar_))

    def _diger_menu(self, dugme, adim_id, yollar_):
        """Kartın ikincil eylemleri tek menüde: klasör, adım raporu, komut."""
        p = self.p
        m = tk.Menu(self.kok, tearoff=False, background=p["kart"], foreground=p["metin"],
                    activebackground=p["secili"], activeforeground=p["metin"])
        rapor = adim_raporu.son_rapor(A.Klasorler(self.ayar).adim_raporlari, adim_id)
        m.add_command(label="Son adım raporunu aç", state="normal" if rapor else "disabled",
                      command=lambda: ac(rapor))
        m.add_command(label="Çıktı klasörünü aç", state="normal" if yollar_ else "disabled",
                      command=lambda: self._klasor_ac(yollar_[0].parent))
        m.add_separator()
        m.add_command(label="Çalışacak komutu kayda yaz", command=lambda: self._komut_goster(adim_id))
        m.tk_popup(dugme.winfo_rootx(), dugme.winfo_rooty() + dugme.winfo_height())

    def _durum_metni(self, adim_id):
        if adim_id in self.adim_durumu:
            return self.adim_durumu[adim_id][1]
        var, zaman = self._cikti_zamanlari.get(adim_id, (False, None)) \
            if hasattr(self, "_cikti_zamanlari") else (False, None)
        if var:
            return f"Son çıktı: {zaman:%d.%m.%Y %H:%M}"
        return "Çıktı yok" if ADIM[adim_id].ciktilar(self.ayar) else ""

    def _listeleri_yenile(self):
        for grup, t in self.listeler.items():
            for adim in grup_adimlari(grup):
                metin = self._durum_metni(adim.id)
                if t.set(adim.id, "durum") != metin:
                    t.set(adim.id, "durum", metin)
                durum = self.adim_durumu.get(adim.id, (None,))[0]
                t.item(adim.id, tags=(durum,) if durum else ())
            if grup == self.etkin_sayfa:
                self._ayrinti_goster(grup)

    # ================================================================ raporlar ve ayarlar
    def _raporlar_sayfasi(self):
        f = ttk.Frame(self.icerik)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)
        sol = ttk.Frame(f, style="Card.TFrame", padding=14)
        sol.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        ttk.Label(sol, text="Raporlar", style="AltBaslik.TLabel").pack(anchor="w", pady=(0, 6))
        self.rapor_sayfa_dugmeleri = []
        for ad, fn in self._rapor_yollari() + [("Program rehberi", lambda: yollar.REPO / "README.md")]:
            d = ttk.Button(sol, text=ad, command=lambda fn=fn: self._yol_ac(fn()))
            d.pack(fill="x", pady=2)
            self.rapor_sayfa_dugmeleri.append((d, fn))
        ttk.Button(sol, text="Sayıları yenile (F5)", command=self._durumu_yenile).pack(fill="x", pady=(12, 0))
        self.ozet_tablo = ttk.Treeview(f, columns=("deger",), show="tree headings")
        self.ozet_tablo.heading("#0", text="Ölçüm", anchor="w")
        self.ozet_tablo.heading("deger", text="Değer", anchor="w")
        self.ozet_tablo.column("#0", width=300)
        self.ozet_tablo.column("deger", width=500)
        self.ozet_tablo.grid(row=0, column=1, sticky="nsew")
        return f

    def _ayarlar_sayfasi(self):
        f = ttk.Frame(self.icerik)
        ust = ttk.Frame(f)
        ust.pack(fill="x", pady=(0, 8))
        ttk.Button(ust, text="Kaydet", style="Accent.TButton", command=self._ayarlari_kaydet).pack(side="left")
        ttk.Button(ust, text="Değişiklikleri geri al", command=self._formu_doldur).pack(side="left", padx=6)
        ttk.Button(ust, text="Bu profili sil", command=self._profil_sil).pack(side="right")
        ic = ttk.Notebook(f)
        ic.pack(fill="both", expand=True)
        ic.add(self._form(ic, SITE_ALANLARI), text="  Site profili  ")
        ic.add(self._form(ic, GENEL_ALANLARI), text="  Yapay zekâ, Bologna, genel  ")
        return f

    def _form(self, ust, bolumler):
        kc = KaydirmaliCerceve(ust)
        for baslik, alanlar in bolumler:
            kart = ttk.Frame(kc.ic, style="Card.TFrame", padding=16)
            kart.pack(fill="x", padx=4, pady=6)
            ttk.Label(kart, text=baslik, style="AltBaslik.TLabel").grid(row=0, column=0, columnspan=3,
                                                                       sticky="w", pady=(0, 6))
            kart.columnconfigure(0, minsize=240)
            kart.columnconfigure(1, weight=1)
            for satir, (anahtar, etiket, tur, yardim, secenekler) in enumerate(alanlar, 1):
                ttk.Label(kart, text=etiket).grid(row=satir, column=0, sticky="w", padx=(0, 12), pady=4)
                w = self._alan(kart, anahtar, tur, secenekler)
                w.grid(row=satir, column=1, sticky="w" if tur == "evet" else "we", pady=4)
                if yardim:
                    ttk.Label(kart, text=yardim, style="Soluk.TLabel", wraplength=330,
                              justify="left").grid(row=satir, column=2, sticky="w", padx=(12, 0))
        return kc

    def _alan(self, ust, anahtar, tur, secenekler):
        if tur == "evet":
            v = tk.BooleanVar()
            self.alanlar[anahtar] = (tur, v)
            return ttk.Checkbutton(ust, variable=v, style="Switch.TCheckbutton")
        if tur == "cok":
            t = tk.Text(ust, height=2, width=50, wrap="word", relief="flat", borderwidth=6,
                        font=(self.yazi, 10))
            self.alanlar[anahtar] = (tur, t)
            return t
        v = tk.StringVar()
        self.alanlar[anahtar] = (tur, v)
        if tur == "secim":
            return ttk.Combobox(ust, textvariable=v, values=secenekler, state="readonly")
        if tur == "secim_yazi":
            return ttk.Combobox(ust, textvariable=v, values=secenekler)
        if tur in ("yol", "dosya"):
            cer = ttk.Frame(ust)
            cer.columnconfigure(0, weight=1)
            ttk.Entry(cer, textvariable=v).grid(row=0, column=0, sticky="we")
            sec = (lambda: filedialog.askdirectory(initialdir=str(A.yol(v.get() or ".")))) if tur == "yol" \
                else (lambda: filedialog.askopenfilename(initialdir=str(A.yol(v.get() or ".").parent)))
            ttk.Button(cer, text="Seç…", command=lambda: (lambda s: s and v.set(s))(sec())
                       ).grid(row=0, column=1, padx=(6, 0))
            return cer
        return ttk.Entry(ust, textvariable=v, show="•" if tur == "gizli" else "")

    # ================================================================ alt panel
    def _durum_seridi(self, ust):
        """En altta her zaman görünen şerit. Çalışırken: dönen gösterge, adım, ilerleme, geçen süre,
        'son hareket' ve Durdur. Araç uzun süre çıktı vermezse sarıya döner ve ne yapılacağını söyler."""
        s = ttk.Frame(ust, style="Card.TFrame", padding=(14, 10))
        s.pack(side="bottom", fill="x", padx=16, pady=(0, 12))
        self.serit = s
        s.columnconfigure(2, weight=1)
        self.canli = ttk.Label(s, text="●", style="Soluk.TLabel", width=2, font=(self.yazi, 15, "bold"))
        self.canli.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 8))
        self.durum_cubugu = ttk.Label(s, text="Hazır.", style="Kalin.TLabel")
        self.durum_cubugu.grid(row=0, column=1, columnspan=2, sticky="w")
        sag = ttk.Frame(s)
        sag.grid(row=0, column=3, sticky="e")
        self.gecen_etiketi = ttk.Label(sag, text="", style="Soluk.TLabel")
        self.gecen_etiketi.pack(side="left", padx=(0, 14))
        self.hata_etiketi = ttk.Label(sag, text="", style="Hata.TLabel", cursor="hand2")
        self.hata_etiketi.pack(side="left", padx=(0, 10))
        self.uyari_etiketi = ttk.Label(sag, text="", style="Uyari.TLabel", cursor="hand2")
        self.uyari_etiketi.pack(side="left", padx=(0, 12))
        for e in (self.hata_etiketi, self.uyari_etiketi):
            e.bind("<Button-1>", lambda _: self._ayrintilar(True, self.sorun_sekmesi))
        self.durdur_dugmesi = ttk.Button(sag, text="■  Durdur", command=self._durdur)
        self.ayrinti_dugmesi = ttk.Button(sag, text="Ayrıntılar  ▴", command=lambda: self._ayrintilar())
        self.ayrinti_dugmesi.pack(side="left")
        self.canlilik = ttk.Label(s, text="Sıradaki adımı ana sayfadan, tek bir adımı ilgili sayfadan başlatın.",
                                  style="Soluk.TLabel", wraplength=760, justify="left")
        self.canlilik.grid(row=1, column=1, columnspan=3, sticky="w", pady=(2, 0))

        self.cubuk_satirlari = []
        for satir, ad in ((2, "Bu adım"), (3, "Toplam")):
            etiket = ttk.Label(s, text=ad, style="Soluk.TLabel", width=9)
            cubuk = ttk.Progressbar(s, maximum=1000, style="Ilerleme.Horizontal.TProgressbar")
            yuzde = ttk.Label(s, text="", style="Yuzde.TLabel" if satir == 2 else "TLabel")
            self.cubuk_satirlari.append((etiket, cubuk, yuzde, satir))
        (_, self.adim_cubugu, self.adim_yuzde, _), (_, self.genel_cubugu, self.genel_yuzde, _) = \
            self.cubuk_satirlari
        self._cubuklari_goster(False)

    def _alt_panel(self, ust):
        self.alt_defter = ttk.Notebook(ust)
        self.alt_defter.pack(fill="both", expand=True, pady=(6, 0))
        self.alt_defter.add(self._kayit_sekmesi(), text="  Çalışma kaydı  ")
        self.sorun_sekmesi = self._sorun_sekmesi()
        self.alt_defter.add(self.sorun_sekmesi, text="  Hatalar ve uyarılar (0)  ")
        self.sonuc_sekmesi = self._sonuc_sekmesi()
        self.alt_defter.add(self.sonuc_sekmesi, text="  Son çalışma: sonuçlar ve çıktılar  ")
        self._yaz(f"Web Denetim Merkezi {SURUM} hazır. Ana sayfadaki 'Başlat' sıradaki adımı çalıştırır; "
                  "tek bir adımı ilgili sayfada seçip 'Çalıştır'a basın.\n")

    def _cubuklari_goster(self, goster):
        for etiket, cubuk, yuzde, satir in self.cubuk_satirlari:
            for w, kol, ek in ((etiket, 1, {}), (cubuk, 2, {}), (yuzde, 3, {})):
                if goster:
                    w.grid(row=satir, column=kol, sticky="we" if w is cubuk else "w",
                           pady=(8 if satir == 2 else 4, 0), padx=(0, 10) if w is not yuzde else 0, **ek)
                else:
                    w.grid_remove()

    def _kayit_sekmesi(self):
        f = ttk.Frame(self.alt_defter, padding=(0, 6, 0, 0))
        ust = ttk.Frame(f)
        ust.pack(fill="x", pady=(0, 6))
        self.kaydir_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ust, text="Yeni satırları takip et", style="Switch.TCheckbutton",
                        variable=self.kaydir_var).pack(side="left")
        self.arama_var = tk.StringVar()
        arama = ttk.Entry(ust, textvariable=self.arama_var, width=26)
        arama.pack(side="left", padx=(18, 6))
        arama.bind("<Return>", lambda _: self._kayitta_ara())
        ttk.Button(ust, text="Kayıtta ara", command=self._kayitta_ara).pack(side="left")
        ttk.Button(ust, text="Temizle", command=lambda: self.kayit.delete("1.0", "end")).pack(side="right")
        ttk.Button(ust, text="Kayıt klasörü",
                   command=lambda: self._klasor_ac(A.Klasorler(self.ayar).kayitlar)).pack(side="right", padx=6)
        cer = ttk.Frame(f)
        cer.pack(fill="both", expand=True)
        self.kayit = tk.Text(cer, wrap="char", height=6, font=(tema.konsol_yazisi(), 9), relief="flat",
                             borderwidth=8, highlightthickness=0)
        self.kayit.tag_configure("vurgu", background="#3b4252")
        kc = ttk.Scrollbar(cer, command=self.kayit.yview)
        self.kayit.configure(yscrollcommand=kc.set)
        self.kayit.pack(side="left", fill="both", expand=True)
        kc.pack(side="right", fill="y")
        return f

    def _sorun_sekmesi(self):
        f = ttk.Frame(self.alt_defter, padding=(0, 6, 0, 0))
        ust = ttk.Frame(f)
        ust.pack(fill="x", pady=(0, 6))
        ttk.Label(ust, text="Çift tıklayınca satır çalışma kaydında gösterilir.",
                  style="Soluk.TLabel").pack(side="left")
        ttk.Button(ust, text="Temizle", command=self._sorunlari_temizle).pack(side="right")
        ttk.Button(ust, text="Panoya kopyala", command=self._sorunlari_kopyala).pack(side="right", padx=6)
        ttk.Button(ust, text="Kayıtta göster", command=self._sorunu_goster).pack(side="right")
        t = ttk.Treeview(f, columns=("zaman", "seviye", "adim", "satir"), show="headings", height=6)
        for kol, baslik, gen in (("zaman", "Saat", 80), ("seviye", "Tür", 70), ("adim", "Adım", 220),
                                 ("satir", "Satır", 800)):
            t.heading(kol, text=baslik, anchor="w")
            t.column(kol, width=gen, stretch=(kol == "satir"))
        kc = ttk.Scrollbar(f, command=t.yview)
        t.configure(yscrollcommand=kc.set)
        t.pack(side="left", fill="both", expand=True)
        kc.pack(side="right", fill="y")
        t.bind("<Double-1>", lambda _: self._sorunu_goster())
        self.sorun_tablo = t
        self.sorun_isaretleri = {}
        return f

    def _sonuc_sekmesi(self):
        f = ttk.Frame(self.alt_defter, padding=(0, 6, 0, 0))
        ust = ttk.Frame(f)
        ust.pack(fill="x", pady=(0, 6))
        self.sonuc_ozet = ttk.Label(ust, text="Henüz çalışma yok.", style="Soluk.TLabel")
        self.sonuc_ozet.pack(side="left", anchor="w")
        ust = ttk.Frame(f)
        ust.pack(fill="x", pady=(0, 6))
        ttk.Label(ust, text="Çıktıyı açmak için çift tıklayın.", style="Soluk.TLabel").pack(side="left")
        ttk.Button(ust, text="Teslim paketi oluştur", command=lambda: self._baslat(["teslim"])).pack(side="right")
        ttk.Button(ust, text="Çıktı klasörü", command=lambda: self._klasor_ac(A.Klasorler(self.ayar).kok)
                   ).pack(side="right", padx=6)
        ttk.Button(ust, text="Bulunduğu klasör", command=lambda: self._sonuc_ac(klasor=True)).pack(side="right")
        ttk.Button(ust, text="Aç", style="Accent.TButton", command=self._sonuc_ac).pack(side="right", padx=6)
        t = ttk.Treeview(f, columns=("durum", "sure", "sorun", "yol"), show="tree headings", height=6)
        t.heading("#0", text="Adım / çıktı", anchor="w")
        for kol, baslik, gen in (("durum", "Durum", 120), ("sure", "Süre", 100), ("sorun", "Hata / uyarı", 110),
                                 ("yol", "Dosya", 520)):
            t.heading(kol, text=baslik, anchor="w")
            t.column(kol, width=gen, stretch=(kol == "yol"))
        t.column("#0", width=300)
        kc = ttk.Scrollbar(f, command=t.yview)
        t.configure(yscrollcommand=kc.set)
        t.pack(side="left", fill="both", expand=True)
        kc.pack(side="right", fill="y")
        t.bind("<Double-1>", lambda _: self._sonuc_ac())
        self.sonuc_tablo = t
        self.sonuc_yollari = {}
        return f

    # ================================================================ tema
    def _tema_degistir(self):
        self.ayar["tema"] = "dark" if self.tema_var.get() else "light"
        self.p = tema.uygula(self.kok, self.ayar["tema"], self.hizli)
        self._tema_renkleri()
        A.kaydet(self.ayar)
        self._durumu_yenile()

    def _tema_renkleri(self):
        p = self.p
        self._yan_boya()
        self.siradaki_serit.configure(background=p["vurgu"])
        self.kayit.configure(background=p["konsol"], foreground=p["konsol_metin"],
                             insertbackground=p["konsol_metin"])
        self.kayit.tag_configure("hata", foreground="#ff7b72")
        self.kayit.tag_configure("uyari", foreground="#e3b341")
        for kc in list(KaydirmaliCerceve.hepsi):
            try:
                kc.renk(p["bg"])
            except tk.TclError:          # kapanmış bir pencereden kalan çerçeve
                KaydirmaliCerceve.hepsi.remove(kc)
        for tur, w in self.alanlar.values():
            if tur == "cok":
                w.configure(background=p["kart"], foreground=p["metin"], insertbackground=p["metin"])
        for t in list(self.listeler.values()) + [self.sonuc_tablo, self.sorun_tablo]:
            t.tag_configure("basarili", foreground=p["basari"])
            t.tag_configure("hatali", foreground=p["hata"])
            t.tag_configure("hata", foreground=p["hata"])
            t.tag_configure("durdu", foreground=p["uyari"])
            t.tag_configure("uyari", foreground=p["uyari"])
            t.tag_configure("baslangic", foreground=p["bilgi"])
        tema.windows_basligi(self.kok, self.ayar.get("tema") == "dark")
        if self.etkin_sayfa == "ana":
            self._ana_sayfayi_doldur(zorla=True)

    # ================================================================ ayarlar
    def _formu_doldur(self):
        for anahtar, (tur, w) in self.alanlar.items():
            deger = self.ayar.get(anahtar, "")
            if tur == "evet":
                w.set(bool(deger))
            elif tur == "cok":
                w.delete("1.0", "end")
                w.insert("1.0", str(deger))
            elif tur in ("sayi", "ondalik"):
                w.set(f"{deger:g}" if isinstance(deger, float) else str(deger))
            else:
                w.set(str(deger))

    def _formu_oku(self):
        """Formu doğrulayıp ayar sözlüğüne yazar. Hata varsa mesaj gösterip False döner."""
        yeni = {}
        for anahtar, (tur, w) in self.alanlar.items():
            if tur == "evet":
                yeni[anahtar] = bool(w.get())
            elif tur == "cok":
                yeni[anahtar] = " ".join(w.get("1.0", "end").split())
            elif tur == "sayi":
                try:
                    yeni[anahtar] = int(w.get().strip() or 0)
                except ValueError:
                    messagebox.showerror("Geçersiz değer", f"'{anahtar}' tam sayı olmalı: {w.get()}")
                    return False
            elif tur == "ondalik":
                try:
                    yeni[anahtar] = float(w.get().strip().replace(",", ".") or 0)
                except ValueError:
                    messagebox.showerror("Geçersiz değer", f"'{anahtar}' sayı olmalı: {w.get()}")
                    return False
            else:
                yeni[anahtar] = w.get().strip()
        if not yeni.get("site_url", "").startswith(("http://", "https://")):
            messagebox.showerror("Geçersiz adres", "Başlangıç adresi http:// veya https:// ile başlamalı.")
            return False
        self.ayar.update(yeni)
        return True

    def _ayarlari_kaydet(self):
        if self.calistirici.calisiyor:
            messagebox.showinfo("Çalışıyor", "Çalışma sürerken ayarlar değiştirilemez.")
            return
        if not self._formu_oku():
            return
        A.kaydet(self.ayar)
        self._profil_yukle_arayuze(formu_doldur=False)
        self._yaz(f"Ayarlar kaydedildi (profil: {self.ayar['aktif_profil']}).\n")
        if (self.ayar.get("arayuz_gorunumu") != "modern") != self.hizli:
            messagebox.showinfo("Görünüm", "Yeni görünüm program yeniden açılınca geçerli olur.")

    def _profil_yukle_arayuze(self, formu_doldur=True):
        self.profil_secim.configure(values=A.profiller())
        self.profil_secim.set(self.ayar["aktif_profil"])
        if formu_doldur:
            self._formu_doldur()
        if self.etkin_sayfa:
            self._sayfa_ac(self.etkin_sayfa)
        self._durumu_yenile()

    def _profil_degisti(self, _=None):
        yeni = self.profil_secim.get()
        if self.calistirici.calisiyor:
            self.profil_secim.set(self.ayar["aktif_profil"])
            messagebox.showinfo("Çalışıyor", "Çalışma sürerken profil değiştirilemez.")
            return
        # Genel ayarları (anahtarlar dahil) koru, yalnızca profili değiştir
        self.ayar.update(A.profil_oku(yeni))
        self.ayar["aktif_profil"] = yeni
        A.kaydet(self.ayar)
        self.adim_durumu.clear()
        self._profil_yukle_arayuze()
        self._yaz(f"Profil: {yeni} ({self.ayar['site_url']})\n")

    def _yeni_site(self):
        if self.calistirici.calisiyor:
            messagebox.showinfo("Çalışıyor", "Çalışma sürerken yeni profil oluşturulamaz.")
            return
        p = tk.Toplevel(self.kok)
        p.title("Yeni site ekle")
        p.transient(self.kok)
        p.resizable(False, False)
        p.configure(background=self.p["bg"])
        cer = ttk.Frame(p, padding=20)
        cer.pack(fill="both")
        ttk.Label(cer, text="Yeni site ekle", style="AltBaslik.TLabel").grid(row=0, column=0, columnspan=2,
                                                                          sticky="w", pady=(0, 10))
        degerler = {}
        for i, (anahtar, etiket, ornek) in enumerate((
            ("url", "Başlangıç adresi", "https://www.ornek.edu.tr/"),
            ("ad", "Profil adı", "Örnek Üniversitesi"),
            ("site_adi", "Raporlardaki site adı", "Örnek Üniversitesi web sitesi"),
            ("bologna_url", "OİBS Bologna adresi (isteğe bağlı)", "obs.ornek.edu.tr  ·  boşsa Mersin Üni."),
        ), 1):
            ttk.Label(cer, text=etiket).grid(row=2 * i - 1, column=0, sticky="w", pady=(6, 0))
            v = tk.StringVar()
            e = ttk.Entry(cer, textvariable=v, width=52)
            e.grid(row=2 * i, column=0, sticky="we")
            ttk.Label(cer, text=f"ör. {ornek}", style="Soluk.TLabel").grid(row=2 * i, column=1, sticky="w", padx=8)
            degerler[anahtar] = v
            if i == 1:
                e.focus_set()
        ttk.Label(cer, text="Çıktılar ciktilar/<profil>/ altına yazılır; mevcut sitelerin verileri "
                            "etkilenmez. Keşif kuralları sonra Ayarlar > Site profili'nden düzenlenir.",
                  style="Soluk.TLabel", wraplength=520, justify="left").grid(row=9, column=0, columnspan=2,
                                                                             pady=12, sticky="w")

        def olustur(_=None):
            url = degerler["url"].get().strip()
            if not url.startswith(("http://", "https://")):
                messagebox.showerror("Geçersiz adres", "Adres http:// veya https:// ile başlamalı.", parent=p)
                return
            ad = degerler["ad"].get().strip() or url
            kimlik = A.profil_kimligi(ad)
            if kimlik in A.profiller() and not messagebox.askyesno(
                    "Profil var", f"'{kimlik}' profili var. Üzerine yazılsın mı?", parent=p):
                return
            kimlik = A.yeni_profil(ad, url, degerler["site_adi"].get().strip(),
                                   bologna_url=degerler["bologna_url"].get().strip())
            p.destroy()
            self.profil_secim.configure(values=A.profiller())
            self.profil_secim.set(kimlik)
            self._profil_degisti()
            self._sayfa_ac("ana")
            self._yaz("Yeni site hazır. Ana sayfadaki yol haritası sıradaki adımı gösterir "
                      "(önce site keşfi).\n")

        d = ttk.Frame(cer)
        d.grid(row=10, column=0, columnspan=2, sticky="e")
        ttk.Button(d, text="Vazgeç", command=p.destroy).pack(side="left", padx=6)
        ttk.Button(d, text="Oluştur", style="Accent.TButton", command=olustur).pack(side="left")
        p.bind("<Return>", olustur)
        p.bind("<Escape>", lambda _: p.destroy())
        p.grab_set()

    def _profil_sil(self):
        pr = self.ayar["aktif_profil"]
        if len(A.profiller()) <= 1:
            messagebox.showinfo("Silinemez", "En az bir profil kalmalı.")
            return
        if not messagebox.askyesno("Profili sil", f"'{pr}' profil dosyası silinsin mi?\n"
                                   "(Çıktı klasörleri silinmez.)"):
            return
        A.profil_dosyasi(pr).unlink(missing_ok=True)
        kalan = A.profiller()[0]
        self.profil_secim.configure(values=A.profiller())
        self.profil_secim.set(kalan)
        self._profil_degisti()

    # ================================================================ çalıştırma
    def _sayfayi_calistir(self, grup):
        """Sayfadaki adımları işaretli bir listede gösterir; seçilenleri sırayla çalıştırır."""
        ids = SAYFA_SIRASI.get(grup) or [a.id for a in grup_adimlari(grup)]
        ad = dict(GRUPLAR)[grup]
        p = tk.Toplevel(self.kok)
        p.title(f"{ad}: sırayla çalıştır")
        p.transient(self.kok)
        p.resizable(False, False)
        p.configure(background=self.p["bg"])
        cer = ttk.Frame(p, padding=20)
        cer.pack(fill="both")
        ttk.Label(cer, text=f"{ad}: sırayla çalıştır", style="AltBaslik.TLabel").pack(anchor="w")
        ttk.Label(cer, text="İşaretli adımlar aşağıdaki sırayla çalışır. İşaretsiz gelenlerin nedeni "
                            "yanında yazıyor.", style="Soluk.TLabel", wraplength=480,
                  justify="left").pack(anchor="w", pady=(2, 10))
        secim = {}
        for i in ids:
            adim = ADIM[i]
            v = tk.BooleanVar(value=i not in ISARETSIZ)
            satir = ttk.Frame(cer)
            satir.pack(anchor="w", fill="x", pady=2)
            ttk.Checkbutton(satir, text=adim.ad + (f"   ({adim.sure})" if adim.sure else ""),
                            variable=v).pack(side="left")
            if i in ISARETSIZ:
                ttk.Label(satir, text=f"   · {ISARETSIZ[i]}", style="Soluk.TLabel").pack(side="left")
            secim[i] = v
        if "gd_etiket" in ids:
            ttk.Label(cer, text=ETIKETLEME_NOTU + " 8a ile 8b birlikte seçilirse 8b çıkarılır.",
                      style="Uyari.TLabel", wraplength=480, justify="left").pack(anchor="w", pady=(10, 0))

        def baslat(_=None):
            secilen = [i for i in ids if secim[i].get()]
            if "gd_etiket" in secilen and "gd_etiket_ozet" in secilen:
                secilen.remove("gd_etiket_ozet")
            if not secilen:
                messagebox.showinfo("Seçim yok", "En az bir adım işaretleyin.", parent=p)
                return
            p.destroy()
            self._baslat(secilen)

        d = ttk.Frame(cer)
        d.pack(anchor="e", pady=(16, 0))
        ttk.Button(d, text="Vazgeç", command=p.destroy).pack(side="left", padx=6)
        ttk.Button(d, text="▶  Başlat", style="Accent.TButton", command=baslat).pack(side="left")
        p.bind("<Return>", baslat)
        p.bind("<Escape>", lambda _: p.destroy())
        p.update_idletasks()             # ana pencerenin ortasında aç
        x = self.kok.winfo_rootx() + (self.kok.winfo_width() - p.winfo_reqwidth()) // 2
        y = self.kok.winfo_rooty() + (self.kok.winfo_height() - p.winfo_reqheight()) // 3
        p.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        p.grab_set()
        return p, secim, baslat

    def _hat(self, ids, baslik="Çalıştır", not_=""):
        if len(ids) > 1:
            adlar = "\n".join(f"  {i + 1}. {ADIM[a].ad}" for i, a in enumerate(ids))
            ek = f"\n\n⚠ {not_}" if not_ else ""
            if not messagebox.askyesno(baslik, f"Şu adımlar sırayla çalışacak:\n\n{adlar}{ek}\n\n"
                                               "Başlatılsın mı?", icon="warning" if not_ else "question"):
                return
        self._baslat(ids)

    def _baslat(self, ids):
        if self.calistirici.calisiyor or (self.is_parcacigi and self.is_parcacigi.is_alive()):
            messagebox.showinfo("Çalışıyor", "Önceki çalışma sürüyor. Bitmesini bekleyin veya durdurun.")
            return
        if not self._formu_oku():
            return
        adimlar = [ADIM[i] for i in ids]
        ayar = dict(self.ayar)   # çalışma sırasında form değişse de bu çalışma etkilenmesin
        for d in self.calistir_dugmeleri:
            d.configure(state="disabled")
        self.durdur_dugmesi.configure(state="normal")
        self.durdur_dugmesi.pack(side="left", padx=(0, 8), before=self.ayrinti_dugmesi)
        self.durum_cubugu.configure(text="Başlatılıyor…")
        self.calisma_bas = self.son_hareket = time.monotonic()
        self.son_ilerleme = None
        self._sorunlari_temizle()
        self.hata_etiketi.configure(text="Hata 0")
        self.uyari_etiketi.configure(text="Uyarı 0")
        self.adim_cubugu["value"] = self.genel_cubugu["value"] = 0
        self.adim_yuzde.configure(text="")
        self.genel_yuzde.configure(text="")
        self._cubuklari_goster(True)
        self.alt_defter.select(0)
        self._saat()
        devam = bool(self.ayar.get("hata_olursa_devam"))

        def is_():
            tamam = self.calistirici.calistir(adimlar, ayar, devam_et=devam)
            self.kuyruk.put(("bitti", tamam, ayar))
        self.is_parcacigi = threading.Thread(target=is_, daemon=True)
        self.is_parcacigi.start()

    def _durdur(self):
        self.durdur_dugmesi.configure(state="disabled")
        self.durum_cubugu.configure(text="Durduruluyor… araç kısmi sonucunu kaydediyor")
        threading.Thread(target=self.calistirici.durdur, daemon=True).start()

    def _komut_goster(self, adim_id):
        if not adim_id or not self._formu_oku():
            return
        adim = ADIM[adim_id]
        self._yaz(f"\n# {adim.ad}: çalıştırılacak komutlar\n")
        try:
            for k in adim.komutlar(self.ayar):
                self._yaz("  " + k.goster() + "\n")
        except Exception as e:
            self._yaz(f"  Komut hazırlanamadı: {e}\n")
        self._ayrintilar(True, 0)

    def _cikti_ac(self, adim_id):
        yollar_ = ADIM[adim_id].ciktilar(self.ayar)
        var = [p for p in yollar_ if p.exists()]
        if var:
            ac(var[0])
        else:
            messagebox.showinfo("Çıktı yok", "Bu adımın çıktısı henüz yok.")

    def _yol_ac(self, p: Path):
        if p.exists():
            ac(p)
        else:
            messagebox.showinfo("Henüz yok", f"Bu çıktı henüz üretilmedi:\n{p}")

    def _klasor_ac(self, p: Path):
        p.mkdir(parents=True, exist_ok=True)
        ac(p)

    # ================================================================ durum
    def _durumu_yenile(self):
        """Durum çıktı dosyalarından hesaplanır. Site haritası ve test sonuçları büyük olabilir;
        arayüz donmasın diye hesap arka planda yapılır, sonuç kuyrukla gelir (_durumu_uygula)."""
        self._durum_kusagi = getattr(self, "_durum_kusagi", 0) + 1
        kusak, ayar = self._durum_kusagi, dict(self.ayar)

        def hesapla():
            try:
                veri = {"zamanlar": adim_durumlari(ayar), "kutular": kutucuklar(ayar),
                        "yol": yol_haritasi(ayar), "ozet": ozet(ayar)}
            except Exception as e:      # bozuk bir çıktı dosyası arayüzü düşürmesin
                veri = {"hata": f"{type(e).__name__}: {e}"}
            self.kuyruk.put(("durum", kusak, veri))

        threading.Thread(target=hesapla, daemon=True).start()

    def _durumu_uygula(self, kusak, veri):
        if kusak != self._durum_kusagi:      # bu arada yenisi istendi
            return
        if "hata" in veri:
            self._yaz(f"Durum okunamadı: {veri['hata']}\n")
            return
        self._cikti_zamanlari = veri["zamanlar"]
        self._listeleri_yenile()
        eski = getattr(self, "_son_durum", None)
        self._son_durum = veri
        if self.etkin_sayfa == "ana":
            self._ana_sayfayi_doldur()
        for d, fn in self.rapor_sayfa_dugmeleri:
            d.configure(state="normal" if fn().exists() else "disabled")
        if eski is not None and eski["ozet"] == veri["ozet"]:
            return
        t = self.ozet_tablo
        t.delete(*t.get_children())
        bolumler = {}
        for bolum, baslik, deger in veri["ozet"]:
            if bolum not in bolumler:
                bolumler[bolum] = t.insert("", "end", text=bolum, open=True)
            t.insert(bolumler[bolum], "end", text=baslik, values=(deger,))

    # ================================================================ kuyruk ve olaylar
    def _yaz_kuyruga(self, metin):
        self.kuyruk.put(("yaz", metin))

    def _olay_kuyruga(self, olay):
        self.kuyruk.put(("olay", olay))

    def _kuyrugu_bosalt(self):
        """Arka plandan gelen iletileri işler. Araçlar saniyede yüzlerce satır yazabilir:
        satırlar tek seferde eklenir, ilerleme ve sayaçtan yalnız sonuncusu çizilir ve her tur
        en fazla ~40 ms sürer; kalan iletiler bir sonraki tura kalır, pencere donmaz."""
        bas = time.monotonic()
        metin, bekleyen = [], {}       # bekleyen: 'ilerleme' / 'sayac' olaylarının sonuncusu

        def bosalt():
            if metin:
                self._yaz("".join(metin))
                metin.clear()
            for tur in ("ilerleme", "sayac"):
                if tur in bekleyen:
                    self._olay(bekleyen.pop(tur))

        try:
            while time.monotonic() - bas < 0.04:
                ileti = self.kuyruk.get_nowait()
                if ileti[0] in ("yaz", "olay"):
                    self.son_hareket = time.monotonic()
                if ileti[0] == "yaz":
                    metin.append(ileti[1])
                    continue
                if ileti[0] == "olay" and ileti[1]["tur"] in ("ilerleme", "sayac"):
                    bekleyen[ileti[1]["tur"]] = ileti[1]
                    continue
                bosalt()               # sıra korunur: önceki satırlar ve ilerleme önce
                if ileti[0] == "olay":
                    self._olay(ileti[1])
                elif ileti[0] == "durum":
                    self._durumu_uygula(ileti[1], ileti[2])
                elif ileti[0] == "ortam":
                    self._ortam_uyarisi(ileti[1])
                elif ileti[0] == "bitti":
                    _, tamam, ayar = ileti
                    if any(r["id"] in ("kurulum", "ortam") for r in self.calistirici.sonuclar):
                        threading.Thread(target=self._ortami_denetle, daemon=True).start()
                    if ayar.get("harita") != self.ayar.get("harita"):   # 'Keşif haritasını kullan'
                        self.ayar["harita"] = ayar["harita"]
                        self._formu_doldur()
                    self._calisma_bitti()
                    self._baslik(f"Web Denetim Merkezi {SURUM}")
                    self._durumu_yenile()
                    self.kok.bell()
        except queue.Empty:
            pass
        finally:
            try:
                bosalt()
            finally:
                self.kok.after(30 if not self.kuyruk.empty() else 100, self._kuyrugu_bosalt)

    def _olay(self, o):
        tur = o["tur"]
        if tur == "basladi":
            self.adim_sayisi = len(o["adimlar"])
        elif tur == "adim_basladi":
            self.durum_cubugu.configure(text=f"Çalışıyor  ·  Adım {o['sira']}/{o['toplam']}  ·  {o['ad']}")
            onceki, self.calisan_grup = self.calisan_grup, ADIM[o["id"]].grup
            for g in {onceki, self.calisan_grup} - {None}:
                self._menu_boya(g)
            self._adim_durum(o["id"], "baslangic", "● Çalışıyor…")
            self.adim_cubugu.configure(mode="indeterminate")
            self.adim_cubugu.start(15)
            self.adim_yuzde.configure(text="ilerleme bilgisi bekleniyor…")
            self.genel_cubugu["value"] = (o["sira"] - 1) / o["toplam"] * 1000
            self.genel_yuzde.configure(text=f"%{(o['sira'] - 1) / o['toplam'] * 100:.0f}  ·  "
                                            f"{o['sira'] - 1}/{o['toplam']} adım tamam")
        elif tur == "ilerleme":
            self.son_ilerleme = o
            if o["biten"] is not None or o["komut_sayisi"] > 1:
                if str(self.adim_cubugu.cget("mode")) != "determinate":
                    self.adim_cubugu.stop()
                    self.adim_cubugu.configure(mode="determinate")
                self.adim_cubugu["value"] = o["oran_adim"] * 1000
                parca = [f"%{o['oran_adim'] * 100:.1f}"]
                if o["biten"] is not None:
                    parca.append(f"{o['biten']:,}/{o['toplam']:,}".replace(",", "."))
                if o["komut_sayisi"] > 1:
                    parca.append(f"parça {o['komut_no']}/{o['komut_sayisi']}")
                parca.append(f"kalan ~{sure_metni(o['kalan_sn'])}")
                self.adim_yuzde.configure(text="  ·  ".join(parca))
                self._adim_durum(o["id"], "baslangic", f"● %{o['oran_adim'] * 100:.0f}")
            self.genel_cubugu["value"] = o["oran_genel"] * 1000
            self.genel_yuzde.configure(text=f"%{o['oran_genel'] * 100:.1f} genel")
            self._baslik(f"%{o['oran_genel'] * 100:.0f} · Web Denetim Merkezi")
        elif tur == "sorun":
            self._sorun_ekle(o)
        elif tur == "sayac":
            self.hata_etiketi.configure(text=f"Hata {o['hata']}")
            self.uyari_etiketi.configure(text=f"Uyarı {o['uyari']}")
        elif tur == "adim_bitti":
            sorun = f" · {o['hata']} hata" if o["hata"] else ""
            self._adim_durum(o["id"], o["sonuc"], f"{DURUM_YAZI[o['sonuc']]} {o['bitis']}{sorun}")
            self.adim_cubugu.stop()
            self.adim_cubugu.configure(mode="determinate")
            if o["sonuc"] == "basarili":
                self.adim_cubugu["value"] = 1000
            self.adim_yuzde.configure(text={"basarili": "%100 · bitti", "hatali": "başarısız",
                                            "durdu": "durduruldu"}[o["sonuc"]] + f" ({sure_metni(o['sure_sn'])})")
        elif tur == "bitti":
            self._sonuclari_goster(o["sonuclar"], o["tamam"])

    def _baslik(self, metin):
        if metin != getattr(self, "_son_baslik", None):
            self._son_baslik = metin
            self.kok.title(metin)

    def _adim_durum(self, adim_id, durum, metin):
        self.adim_durumu[adim_id] = (durum, metin)
        grup = ADIM[adim_id].grup
        t = self.listeler.get(grup)
        if t:
            t.set(adim_id, "durum", metin)
            t.item(adim_id, tags=(durum,))
            if t.focus() == adim_id:
                self._ayrinti_goster(grup)

    def _saat(self):
        """Çalışırken dört kez saniyede: dönen gösterge, geçen süre ve 'son hareket'. Araç uzun süre
        hiç çıktı vermezse gösterge sarıya döner ve ne yapılacağını söyler."""
        if self.calisma_bas is None:
            return
        simdi = time.monotonic()
        self.canli_kare += 1
        sessiz = simdi - (self.son_hareket or simdi)
        stil = "Canli.TLabel" if sessiz < SESSIZ_UYARI_SN else "CanliUyari.TLabel"
        self.canli.configure(text=CANLI_KARE[self.canli_kare % 4], style=stil)
        self.gecen_etiketi.configure(text=f"Geçen {sure_metni(simdi - self.calisma_bas)}")
        if sessiz < 5:
            metin = "Program çalışıyor  ·  araç az önce çıktı verdi"
        elif sessiz < SESSIZ_UYARI_SN:
            metin = f"Program çalışıyor  ·  son hareket {sure_metni(sessiz)} önce"
        elif sessiz < SESSIZ_CIDDI_SN:
            metin = (f"Son çıktı {sure_metni(sessiz)} önce. Bazı adımlar uzun sürer; "
                     "gösterge dönüyorsa program çalışıyor ve bekliyor.")
        else:
            metin = (f"Son çıktı {sure_metni(sessiz)} önce; takılmış olabilir. 'Durdur'a basıp adımı "
                     "yeniden başlatın (biten işler atlanır).")
        self.canlilik.configure(text=metin, style="Soluk.TLabel" if sessiz < SESSIZ_UYARI_SN else "Uyari.TLabel")
        if self.calisan_grup and self.canli_kare % 2 == 0:
            self._menu_boya(self.calisan_grup)
        self.kok.after(250, self._saat)

    def _calisma_bitti(self):
        self.calisma_bas = None
        for d in self.calistir_dugmeleri:
            d.configure(state="normal")
        self.durdur_dugmesi.pack_forget()
        grup, self.calisan_grup = self.calisan_grup, None
        if grup:
            self._menu_boya(grup)
        self._baslik(f"Web Denetim Merkezi {SURUM}")
        for g in self.listeler:
            if g == self.etkin_sayfa:
                self._ayrinti_goster(g)

    # ================================================================ hatalar ve uyarılar
    def _sorun_ekle(self, o):
        self.sorun_sayisi += 1
        isaret = None
        aranan = o["satir"][:80]
        if aranan:
            konum = self.kayit.search(aranan, "end", backwards=True, stopindex="end-600l")
            if konum:
                isaret = f"sorun{self.sorun_sayisi}"
                self.kayit.mark_set(isaret, konum)
                self.kayit.mark_gravity(isaret, "left")
                self.kayit.tag_add(o["seviye"], f"{konum} linestart", f"{konum} lineend")
        oge = self.sorun_tablo.insert("", "end", tags=(o["seviye"],), values=(
            o["zaman"], "Hata" if o["seviye"] == "hata" else "Uyarı", o["ad"], o["satir"]))
        if isaret:
            self.sorun_isaretleri[oge] = isaret
        self.sorun_tablo_sayisi = getattr(self, "sorun_tablo_sayisi", 0) + 1
        n = self.sorun_tablo_sayisi
        self.alt_defter.tab(self.sorun_sekmesi, text=f"  Hatalar ve uyarılar ({n})  ")

    def _sorunu_goster(self):
        secim = self.sorun_tablo.selection()
        if not secim:
            return
        isaret = self.sorun_isaretleri.get(secim[0])
        if not isaret or isaret not in self.kayit.mark_names():
            messagebox.showinfo("Bulunamadı", "Bu satır kayıtta artık yok (eski satırlar silinmiş olabilir). "
                                              "Kayıt klasöründeki dosyaya bakın.")
            return
        self.kaydir_var.set(False)
        self._ayrintilar(True, 0)
        self.kayit.tag_remove("vurgu", "1.0", "end")
        self.kayit.tag_add("vurgu", f"{isaret} linestart", f"{isaret} lineend+1c")
        self.kayit.see(isaret)

    def _sorunlari_temizle(self):
        self.sorun_tablo.delete(*self.sorun_tablo.get_children())
        self.sorun_isaretleri.clear()
        self.sorun_tablo_sayisi = 0
        self.alt_defter.tab(self.sorun_sekmesi, text="  Hatalar ve uyarılar (0)  ")

    def _sorunlari_kopyala(self):
        satirlar = ["\t".join(map(str, self.sorun_tablo.item(i, "values")))
                    for i in self.sorun_tablo.get_children()]
        self.kok.clipboard_clear()
        self.kok.clipboard_append("\n".join(satirlar))

    def _kayitta_ara(self):
        aranan = self.arama_var.get()
        if not aranan:
            return
        bas = self.kayit.index("insert") if self.kayit.tag_ranges("vurgu") else "end"
        konum = self.kayit.search(aranan, bas, backwards=True, nocase=True)
        if not konum:
            self.kok.bell()
            return
        self.kaydir_var.set(False)
        self.kayit.tag_remove("vurgu", "1.0", "end")
        self.kayit.tag_add("vurgu", konum, f"{konum}+{len(aranan)}c")
        self.kayit.mark_set("insert", konum)
        self.kayit.see(konum)

    # ================================================================ son çalışma
    def _etiketleme_hatirlat(self):
        """Zincir 8a'yı da çalıştırdıysa: sıra kullanıcıda, etiketleme sayfasını açmayı öner."""
        sayfa = A.Klasorler(self.ayar).etiket / "etiketle.html"
        if messagebox.askyesno("Etiketleme sizde",
                               "Etiketleme sayfası hazır. Bulguları 1 Gerçek / 2 Yanlış / 3 Emin değilim ile "
                               "işaretleyip 'CSV indir'e basın. Sonra ana sayfada Başlat, etiketleri işler (8b).\n\n"
                               "Etiketleme sayfası şimdi açılsın mı?"):
            self._yol_ac(sayfa)

    def _sonuclari_goster(self, sonuclar, tamam):
        t = self.sonuc_tablo
        t.delete(*t.get_children())
        self.sonuc_yollari = {}       # tablo satırı -> tam dosya yolu
        for r in sonuclar:
            ust = t.insert("", "end", text=r["ad"], open=True, tags=(r["sonuc"],), values=(
                DURUM_YAZI[r["sonuc"]], sure_metni(r["sure_sn"]), f"{r['hata']} / {r['uyari']}", ""))
            if r.get("rapor"):
                oge = t.insert(ust, "end", text="    Adım raporu", values=("rapor", "", "", _kisa_yol(r["rapor"])))
                self.sonuc_yollari[oge] = r["rapor"]
            for yol in r["ciktilar"]:
                oge = t.insert(ust, "end", text="    " + Path(yol).name, values=("çıktı", "", "", _kisa_yol(yol)))
                self.sonuc_yollari[oge] = yol
            if r["kayit"]:
                oge = t.insert(ust, "end", text="    Çalışma kaydı", values=("kayıt", "", "", _kisa_yol(r["kayit"])))
                self.sonuc_yollari[oge] = r["kayit"]
        basarili = sum(r["sonuc"] == "basarili" for r in sonuclar)
        durdu = any(r["sonuc"] == "durdu" for r in sonuclar)
        hata = sum(r["hata"] for r in sonuclar)
        uyari = sum(r["uyari"] for r in sonuclar)
        toplam_sure = sum(r["sure_sn"] for r in sonuclar)
        ozet_metni = (f"{len(sonuclar)} adımdan {basarili} başarılı · {hata} hata, {uyari} uyarı · "
                      f"toplam {sure_metni(toplam_sure)}")
        self.sonuc_ozet.configure(text=ozet_metni,
                                  style="Kalin.TLabel" if tamam else "Hata.TLabel")
        if tamam:
            bas, stil, isaret = "Bitti", "CanliBasari.TLabel", "✔"
        elif durdu:
            bas, stil, isaret = "Durduruldu", "CanliUyari.TLabel", "■"
        else:
            bas, stil, isaret = "Bitti, sorun var", "CanliHata.TLabel", "✖"
        self.canli.configure(text=isaret, style=stil)
        self.durum_cubugu.configure(text=f"{bas}  ·  {ozet_metni}")
        if any(r["id"] == "gd_etiket" and r["sonuc"] == "basarili" for r in sonuclar) and len(sonuclar) > 1:
            self.kok.after(300, self._etiketleme_hatirlat)
        self.canlilik.configure(text="Çıktılar için 'Ayrıntılar' > Son çalışma; raporlar ana sayfada.",
                                style="Soluk.TLabel")
        calisan = len(sonuclar) / max(self.adim_sayisi or len(sonuclar), 1)
        self.genel_cubugu["value"] = calisan * 1000
        self.genel_yuzde.configure(text=f"%{calisan * 100:.0f} · " + (
            "tamamlandı" if tamam else f"{len(sonuclar)} adım çalıştı, {len(sonuclar) - basarili} sorunlu"))
        self._cubuklari_goster(False)
        self.gecen_etiketi.configure(text=f"Toplam {sure_metni(toplam_sure)}")
        if not tamam and not durdu:    # sorun varsa ayrıntılar kendiliğinden açılır
            self._ayrintilar(True, self.sorun_sekmesi if self.sorun_tablo.get_children() else self.sonuc_sekmesi)
        else:
            self.alt_defter.select(self.sonuc_sekmesi)

    def _sonuc_ac(self, klasor=False):
        secim = self.sonuc_tablo.selection()
        if not secim:
            return
        oge = secim[0]
        yol = self.sonuc_yollari.get(oge, "")
        if not yol:   # adım satırı seçildiyse ilk çıktısını aç
            cocuklar = self.sonuc_tablo.get_children(oge)
            yol = self.sonuc_yollari.get(cocuklar[0], "") if cocuklar else ""
        if not yol:
            messagebox.showinfo("Çıktı yok", "Bu adımın açılacak bir çıktısı yok.")
            return
        p = Path(yol)
        self._yol_ac(p.parent if klasor else p)

    def _yaz(self, metin):
        k = self.kayit
        en_altta = k.yview()[1] > 0.999
        parcalar = metin.replace("\r\n", "\n").split("\r")
        for i, p in enumerate(parcalar):
            if i > 0:   # \r: satır başına dön (ilerleme çubukları aynı satırı günceller)
                k.delete("end-1c linestart", "end-1c")
            k.insert("end", p)
        satir = int(k.index("end-1c").split(".")[0])
        if satir > 20000:
            k.delete("1.0", f"{satir - 15000}.0")
        if en_altta and self.kaydir_var.get():
            k.see("end")

    def _kapat(self):
        if self.calistirici.calisiyor and not messagebox.askyesno(
                "Çıkış", "Bir çalışma sürüyor. Durdurup çıkılsın mı?"):
            return
        self.calistirici.durdur()
        self.kok.destroy()


def baslat(ayar: dict):
    if os.name == "nt":   # yüksek çözünürlüklü ekranlarda bulanık yazıyı önler (Tk'den önce)
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    try:
        kok = tk.Tk()
    except tk.TclError as e:
        sys.exit(f"Arayüz açılamadı ({e}). Komut satırı için: python web_denetim.py --help")
    Uygulama(kok, ayar)
    kok.mainloop()
