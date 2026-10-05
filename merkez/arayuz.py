"""Web Denetim Merkezi masaüstü arayüzü (Tkinter; Python ile birlikte gelir).

Düzen: solda menü (profil, sayfalar, tema), sağda sayfa içeriği; altta ilerleme paneli
ve çalışma kaydı / hatalar / son çalışma sekmeleri. Görünüm `tema.py`'de.
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

from . import SURUM, tema, yollar
from . import ayarlar as A
from .adimlar import ADIM, ADIMLAR, AI_HATTI, GRUPLAR, grup_adimlari, tam_hat
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
    ("Yapay zekâ talimatı", [
        ("site_tanimi", "Site tanımı (İngilizce)", "metin",
         "Modele 'You are a UI QA reviewer for ...' diye verilir.", None),
        ("site_dili", "Sitenin dili (İngilizce)", "metin", "Ör. Turkish, English, German", None),
    ]),
    ("Bologna (OİBS)", [
        ("bologna_url", "OİBS Bologna adresi", "metin",
         "OİBS kullanan herhangi bir üniversitenin Bologna kök adresi.", None),
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
}
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


class KaydirmaliCerceve(ttk.Frame):
    """İçeriği dikey kaydırılabilen çerçeve."""
    hepsi = []

    def __init__(self, ust, **kw):
        super().__init__(ust, **kw)
        self.tuval = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        cubuk = ttk.Scrollbar(self, orient="vertical", command=self.tuval.yview)
        self.ic = ttk.Frame(self.tuval)
        self.ic.bind("<Configure>", lambda e: self.tuval.configure(scrollregion=self.tuval.bbox("all")))
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
        self.secili = set()              # çalıştırılmak üzere işaretli adımlar
        self.adim_durumu = {}            # bu oturumda: adım id -> (durum, metin)
        self.listeler = {}               # grup -> Treeview
        self.ayrinti = {}                # grup -> ayrıntı paneli parçaları
        self.alanlar = {}                # ayar anahtarı -> (tür, değişken/widget)
        self.sayfalar = {}               # sayfa adı -> çerçeve
        self.menu_ogeleri = {}           # sayfa adı -> etiket
        self.etkin_sayfa = None

        kok.title(f"Web Denetim Merkezi {SURUM}")
        kok.geometry("1320x900")
        kok.minsize(1040, 700)
        self.p = tema.uygula(kok, self.ayar.get("tema", "light"))
        self.yazi = tema.yazi_ailesi()
        self._iskelet()
        self._profil_yukle_arayuze()
        self._sayfa_ac("ana")
        self._tema_renkleri()
        kok.after(200, self._bolmeyi_ayarla)
        self.ortam_sorunlari = []
        threading.Thread(target=self._ortami_denetle, daemon=True).start()
        kok.after(100, self._kuyrugu_bosalt)
        kok.protocol("WM_DELETE_WINDOW", self._kapat)
        kok.bind("<Control-Return>", lambda _: self._secilenleri_calistir())
        kok.bind("<F5>", lambda _: self._durumu_yenile())

    # ================================================================ iskelet
    def _iskelet(self):
        kap = ttk.Frame(self.kok)
        kap.pack(fill="both", expand=True)
        self._yan_menu(kap)
        sag = ttk.Frame(kap)
        sag.pack(side="left", fill="both", expand=True)
        self._ust_cubuk(sag)
        bol = ttk.PanedWindow(sag, orient="vertical")
        bol.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.bolme = bol
        self.icerik = ttk.Frame(bol)
        bol.add(self.icerik, weight=5)
        alt = ttk.Frame(bol)
        bol.add(alt, weight=3)
        self._alt_panel(alt)

        self.sayfalar["ana"] = self._ana_sayfa()
        for grup, _ in GRUPLAR:
            self.sayfalar[grup] = self._grup_sayfasi(grup)
        self.sayfalar["raporlar"] = self._raporlar_sayfasi()
        self.sayfalar["ayarlar"] = self._ayarlar_sayfasi()

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
        surum = tk.Label(y, text=f"Sürüm {SURUM}" + ("" if tema.sv_ttk_var() else " · temel tema"),
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
        self.menu_ogeleri[ad].configure(
            background=p["secili"] if secili else (p["kenar"] if uzerinde else p["yan"]),
            foreground=p["metin"], font=(self.yazi, 10, "bold" if secili else "normal"))

    def _ust_cubuk(self, ust):
        c = ttk.Frame(ust, padding=(16, 14, 16, 10))
        c.pack(fill="x")
        sag = ttk.Frame(c)            # önce sağ: dar pencerede düğmeler değil açıklama kısalır
        sag.pack(side="right", anchor="n")
        sol = ttk.Frame(c)
        sol.pack(side="left", fill="x", expand=True)
        self.sayfa_basligi = ttk.Label(sol, text="", style="Baslik.TLabel")
        self.sayfa_basligi.pack(anchor="w")
        self.sayfa_alt = ttk.Label(sol, text="", style="Soluk.TLabel", wraplength=520, justify="left")
        self.sayfa_alt.pack(anchor="w")
        sol.bind("<Configure>", lambda e: self.sayfa_alt.configure(wraplength=max(e.width - 10, 200)))
        self.calistir_dugmesi = ttk.Button(sag, text="▶  Seçilenleri çalıştır", style="Accent.TButton",
                                           command=self._secilenleri_calistir)
        self.calistir_dugmesi.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(sag, text="Tam hat", command=lambda: self._hat(tam_hat(self.ayar))).grid(row=0, column=1)
        ttk.Button(sag, text="Yapay zekâ hattı", command=lambda: self._hat(AI_HATTI)).grid(row=0, column=2, padx=6)
        self.durdur_dugmesi = ttk.Button(sag, text="■  Durdur", command=self._durdur, state="disabled")
        self.durdur_dugmesi.grid(row=0, column=3)
        self.devam_var = tk.BooleanVar(value=self.ayar["hata_olursa_devam"])
        ttk.Checkbutton(sag, text="Hata olursa sonraki adımlarla sürdür", style="Switch.TCheckbutton",
                        variable=self.devam_var,
                        command=lambda: self.ayar.update(hata_olursa_devam=self.devam_var.get())
                        ).grid(row=1, column=0, columnspan=4, sticky="e", pady=(6, 0))

    def _bolmeyi_ayarla(self, oran=0.6):
        """Boştayken içeriğe, çalışırken kayda daha çok yer ver."""
        self.kok.update_idletasks()
        h = self.bolme.winfo_height()
        if h > 200:
            self.bolme.sashpos(0, int(h * oran))

    def _sayfa_ac(self, ad):
        if self.etkin_sayfa:
            self.sayfalar[self.etkin_sayfa].pack_forget()
        self.etkin_sayfa = ad
        self.sayfalar[ad].pack(fill="both", expand=True)
        for a in self.menu_ogeleri:
            self._menu_boya(a)
        basliklar = dict(GRUPLAR)
        basliklar.update(ana="Ana sayfa", raporlar="Raporlar ve özet", ayarlar="Ayarlar")
        self.sayfa_basligi.configure(text=basliklar[ad])
        alt = {"ana": f'{self.ayar["site_adi"]}  ·  {self.ayar["site_url"]}',
               "raporlar": "Çıktılardan özet sayılar ve raporlar.",
               "ayarlar": "Site profili seçili siteye, diğer ayarlar tüm sitelere uygulanır."}
        self.sayfa_alt.configure(text=alt.get(ad, SAYFA_ACIKLAMA.get(ad, "")))
        if ad in ("ana", "raporlar"):
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
        self.uyari_metni = ttk.Label(self.uyari_karti, text="", style="Uyari.TLabel", justify="left")
        self.uyari_metni.pack(side="left", anchor="w")
        ttk.Button(self.uyari_karti, text="Ortam kontrolü", command=lambda: self._baslat(["ortam"])
                   ).pack(side="right")
        ttk.Button(self.uyari_karti, text="▶  Bağımlılıkları kur", style="Accent.TButton",
                   command=lambda: self._baslat(["kurulum", "ortam"])).pack(side="right", padx=6)
        self.kutu_cercevesi = ttk.Frame(f)
        self.kutu_cercevesi.pack(fill="x", pady=(0, 12))

        govde = ttk.Frame(f)
        govde.pack(fill="both", expand=True)
        govde.columnconfigure(0, weight=3)
        govde.columnconfigure(1, weight=2)

        yh = ttk.Frame(govde, style="Card.TFrame", padding=16)
        yh.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(yh, text="Yol haritası", style="AltBaslik.TLabel").pack(anchor="w")
        ttk.Label(yh, text="Önerilen sıra. Tamamlanan aşamalar işaretlidir; sıradakini tek tıkla başlatın.",
                  style="Soluk.TLabel").pack(anchor="w", pady=(0, 8))
        self.yol_cercevesi = ttk.Frame(yh)
        self.yol_cercevesi.pack(fill="x")

        sag = ttk.Frame(govde)
        sag.grid(row=0, column=1, sticky="nsew")
        rk = ttk.Frame(sag, style="Card.TFrame", padding=16)
        rk.pack(fill="x")
        ttk.Label(rk, text="Raporlar", style="AltBaslik.TLabel").pack(anchor="w")
        ttk.Label(rk, text="Üretilmiş raporlar açılabilir.", style="Soluk.TLabel").pack(anchor="w", pady=(0, 8))
        self.rapor_dugmeleri = []
        for ad, fn in self._rapor_yollari():
            d = ttk.Button(rk, text=ad, command=lambda fn=fn: self._yol_ac(fn()))
            d.pack(fill="x", pady=2)
            self.rapor_dugmeleri.append((d, fn))

        ip = ttk.Frame(sag, style="Card.TFrame", padding=16)
        ip.pack(fill="x", pady=(12, 0))
        ttk.Label(ip, text="İpuçları", style="AltBaslik.TLabel").pack(anchor="w")
        for metin in ("Adım sayfalarında satırın başındaki kutuya tıklayarak birden fazla adımı "
                      "seçin, Ctrl+Enter ile çalıştırın.",
                      "Uzun işler yarıda kalırsa aynı adımı tekrar çalıştırın; araçlar kaldığı "
                      "yerden devam eder.",
                      "Başka bir site için sol menüden 'Yeni site ekle'yi kullanın."):
            ttk.Label(ip, text="•  " + metin, wraplength=330, justify="left").pack(anchor="w", pady=2)
        return kc

    def _ortam_uyarisi(self, sorunlar):
        self.ortam_sorunlari = sorunlar
        if sorunlar:
            self.uyari_metni.configure(text="Bu bilgisayarda kurulum eksik:\n" +
                                       "\n".join(f"•  {s}" for s in sorunlar))
            self.uyari_karti.pack(fill="x", pady=(0, 12), before=self.kutu_cercevesi)
            self._yaz("⚠ Kurulum eksik: " + "; ".join(sorunlar) +
                      ". Ana sayfadaki 'Bağımlılıkları kur' düğmesini kullanın.\n")
        else:
            self.uyari_karti.pack_forget()

    def _rapor_yollari(self):
        k = lambda: A.Klasorler(self.ayar)  # noqa: E731
        return [
            ("Kanıtlı test raporu", lambda: k().test / "report.html"),
            ("Deneme testi raporu", lambda: k().deneme / "report.html"),
            ("Görsel kusur raporu", lambda: k().gorsel / "gorsel_rapor.html"),
            ("Yapay zekâ son raporu", lambda: k().ai_rapor / "rapor.html"),
            ("Teslim paketi", lambda: k().teslim / "index.html"),
            ("Çıktı klasörü", lambda: k().kok),
        ]

    def _ana_sayfayi_doldur(self):
        for w in self.kutu_cercevesi.winfo_children():
            w.destroy()
        for i, (baslik, deger, alt, vurgu) in enumerate(kutucuklar(self.ayar)):
            kutu = ttk.Frame(self.kutu_cercevesi, style="Card.TFrame", padding=(16, 12))
            kutu.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            self.kutu_cercevesi.columnconfigure(i, weight=1, uniform="kutu")
            ttk.Label(kutu, text=baslik, style="Soluk.TLabel").pack(anchor="w")
            stil = {"vurgu": "SayiVurgu.TLabel", "hata": "SayiHata.TLabel"}.get(vurgu, "Sayi.TLabel")
            ttk.Label(kutu, text=deger, style=stil).pack(anchor="w")
            ttk.Label(kutu, text=alt, style="Soluk.TLabel").pack(anchor="w")

        for w in self.yol_cercevesi.winfo_children():
            w.destroy()
        onerilen = None
        for i, (baslik, aciklama, tamam, ayrinti, ids) in enumerate(yol_haritasi(self.ayar)):
            if not tamam and onerilen is None:
                onerilen = i
            satir = ttk.Frame(self.yol_cercevesi, padding=(0, 6))
            satir.pack(fill="x")
            satir.columnconfigure(1, weight=1)
            isaret = "✔" if tamam else ("▶" if i == onerilen else "○")
            ttk.Label(satir, text=isaret, width=2, font=(self.yazi, 13, "bold"),
                      foreground=self.p["basari"] if tamam else (self.p["vurgu"] if i == onerilen
                                                                 else self.p["soluk"])
                      ).grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8))
            ttk.Label(satir, text=f"{i + 1}. {baslik}" + (f"   ·  {ayrinti}" if ayrinti else ""),
                      style="Kalin.TLabel").grid(row=0, column=1, sticky="w")
            ttk.Label(satir, text=aciklama, style="Soluk.TLabel").grid(row=1, column=1, sticky="w")
            ttk.Button(satir, text="Çalıştır" if i != onerilen else "▶  Sıradaki: çalıştır",
                       style="Accent.TButton" if i == onerilen else "TButton",
                       command=lambda ids=ids, b=baslik: self._hat(ids, b)
                       ).grid(row=0, column=2, rowspan=2, sticky="e")
        for d, fn in self.rapor_dugmeleri:
            d.configure(state="normal" if fn().exists() else "disabled")

    # ================================================================ adım sayfaları
    def _grup_sayfasi(self, grup):
        f = ttk.Frame(self.icerik)
        f.columnconfigure(0, weight=3)
        f.columnconfigure(1, weight=2)
        f.rowconfigure(0, weight=1)

        sol = ttk.Frame(f)
        sol.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        t = ttk.Treeview(sol, columns=("sec", "ad", "sure", "durum"), show="headings", selectmode="browse")
        for kol, baslik, gen, uzar in (("sec", "", 36, False), ("ad", "Adım", 300, True),
                                       ("sure", "Tahmini süre", 120, False),
                                       ("durum", "Durum", 210, False)):
            t.heading(kol, text=baslik, anchor="w")
            t.column(kol, width=gen, stretch=uzar, anchor="center" if kol == "sec" else "w")
        for adim in grup_adimlari(grup):
            t.insert("", "end", iid=adim.id, values=("☐", adim.ad, adim.sure or "", ""))
        kc = ttk.Scrollbar(sol, command=t.yview)
        t.configure(yscrollcommand=kc.set)
        t.pack(side="left", fill="both", expand=True)
        kc.pack(side="right", fill="y")
        t.bind("<<TreeviewSelect>>", lambda _, g=grup: self._ayrinti_goster(g))
        t.bind("<Button-1>", lambda e, tv=t: self._liste_tiklama(e, tv))
        t.bind("<space>", lambda _, tv=t: self._sec_degistir(tv, tv.focus()))
        t.bind("<Double-1>", lambda e, tv=t: (None if tv.identify_column(e.x) == "#1"
                                              else self._baslat([tv.focus()]) if tv.focus() else None))
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
        cikti = ttk.Button(dugmeler, text="Çıktıyı aç")
        cikti.pack(side="left", padx=6)
        klasor = ttk.Button(dugmeler, text="Klasörü aç")
        klasor.pack(side="left")
        ttk.Button(kart, text="Çalışacak komutu kayda yaz",
                   command=lambda g=grup: self._komut_goster(self.listeler[g].focus())
                   ).pack(anchor="w", pady=(8, 0))
        ipucu = ttk.Label(kart, text="İpucu: satırın başındaki kutuyla birden fazla adımı seçip üstteki "
                                     "'Seçilenleri çalıştır'ı kullanın. Çift tıklama adımı çalıştırır.",
                          style="Soluk.TLabel", wraplength=380, justify="left")
        ipucu.pack(side="bottom", anchor="w")
        kart.bind("<Configure>", lambda e, ls=(baslik, aciklama, ciktilar, ipucu): [
            l.configure(wraplength=max(e.width - 40, 200)) for l in ls])
        self.ayrinti[grup] = dict(baslik=baslik, durum=durum, aciklama=aciklama, ciktilar=ciktilar,
                                  calistir=calistir, cikti=cikti, klasor=klasor)
        ilk = grup_adimlari(grup)[0].id
        t.selection_set(ilk)
        t.focus(ilk)
        return f

    def _liste_tiklama(self, e, tv):
        if tv.identify_region(e.x, e.y) == "cell" and tv.identify_column(e.x) == "#1":
            oge = tv.identify_row(e.y)
            if oge:
                self._sec_degistir(tv, oge)
                return "break"

    def _sec_degistir(self, tv, oge):
        if not oge:
            return
        if oge in self.secili:
            self.secili.discard(oge)
        else:
            self.secili.add(oge)
        tv.set(oge, "sec", "☑" if oge in self.secili else "☐")
        self._secim_sayisi()

    def _secim_sayisi(self):
        n = len(self.secili)
        self.calistir_dugmesi.configure(text=f"▶  Seçilenleri çalıştır ({n})" if n else "▶  Seçilenleri çalıştır")

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
            a["ciktilar"].configure(text="Bu adım dosya üretmez; sonuç çalışma kaydında görünür.")
        var = [p for p in yollar_ if p.exists()]
        a["calistir"].configure(command=lambda: self._baslat([adim_id]))
        a["cikti"].configure(state="normal" if var else "disabled", command=lambda: self._cikti_ac(adim_id))
        a["klasor"].configure(state="normal" if yollar_ else "disabled",
                              command=lambda: self._klasor_ac(yollar_[0].parent))

    def _durum_metni(self, adim_id):
        if adim_id in self.adim_durumu:
            return self.adim_durumu[adim_id][1]
        var, zaman = self._cikti_zamanlari.get(adim_id, (False, None)) \
            if hasattr(self, "_cikti_zamanlari") else (False, None)
        if var:
            return f"Son çıktı: {zaman:%d.%m.%Y %H:%M}"
        return "Çıktı yok" if ADIM[adim_id].ciktilar(self.ayar) else ""

    def _listeleri_yenile(self):
        self._cikti_zamanlari = adim_durumlari(self.ayar)
        for grup, t in self.listeler.items():
            for adim in grup_adimlari(grup):
                t.set(adim.id, "durum", self._durum_metni(adim.id))
                durum = self.adim_durumu.get(adim.id, (None,))[0]
                t.item(adim.id, tags=(durum,) if durum else ())
            self._ayrinti_goster(grup)

    # ================================================================ raporlar ve ayarlar
    def _raporlar_sayfasi(self):
        f = ttk.Frame(self.icerik)
        dugmeler = ttk.Frame(f)
        dugmeler.pack(fill="x", pady=(0, 8))
        ttk.Button(dugmeler, text="Yenile (F5)", command=self._durumu_yenile).pack(side="left")
        for ad, fn in self._rapor_yollari() + [("Program rehberi", lambda: yollar.REPO / "README.md")]:
            ttk.Button(dugmeler, text=ad, command=lambda fn=fn: self._yol_ac(fn())).pack(side="left", padx=(6, 0))
        self.ozet_tablo = ttk.Treeview(f, columns=("deger",), show="tree headings")
        self.ozet_tablo.heading("#0", text="Ölçüm", anchor="w")
        self.ozet_tablo.heading("deger", text="Değer", anchor="w")
        self.ozet_tablo.column("#0", width=320)
        self.ozet_tablo.column("deger", width=700)
        self.ozet_tablo.pack(fill="both", expand=True)
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
    def _alt_panel(self, ust):
        self.ilerleme = ttk.Frame(ust, style="Card.TFrame", padding=(14, 10))
        self.ilerleme.pack(fill="x", pady=(8, 8))
        f = self.ilerleme
        f.columnconfigure(1, weight=1)
        self.durum_cubugu = ttk.Label(f, text="Hazır. Bir adım seçip çalıştırın.", style="Kalin.TLabel")
        self.durum_cubugu.grid(row=0, column=0, columnspan=3, sticky="w")
        sayac = ttk.Frame(f)
        sayac.grid(row=0, column=3, sticky="e")
        self.gecen_etiketi = ttk.Label(sayac, text="", style="Soluk.TLabel")
        self.gecen_etiketi.pack(side="left", padx=(0, 14))
        self.hata_etiketi = ttk.Label(sayac, text="Hata 0", style="Hata.TLabel", cursor="hand2")
        self.hata_etiketi.pack(side="left", padx=(0, 10))
        self.uyari_etiketi = ttk.Label(sayac, text="Uyarı 0", style="Uyari.TLabel", cursor="hand2")
        self.uyari_etiketi.pack(side="left")
        for e in (self.hata_etiketi, self.uyari_etiketi):
            e.bind("<Button-1>", lambda _: self.alt_defter.select(self.sorun_sekmesi))

        self.cubuk_satirlari = []
        for satir, ad in ((1, "Bu adım"), (2, "Toplam")):
            etiket = ttk.Label(f, text=ad, style="Soluk.TLabel", width=9)
            cubuk = ttk.Progressbar(f, maximum=1000, style="Ilerleme.Horizontal.TProgressbar")
            yuzde = ttk.Label(f, text="", style="Yuzde.TLabel" if satir == 1 else "TLabel")
            self.cubuk_satirlari.append((etiket, cubuk, yuzde, satir))
        (_, self.adim_cubugu, self.adim_yuzde, _), (_, self.genel_cubugu, self.genel_yuzde, _) = \
            self.cubuk_satirlari
        self._cubuklari_goster(False)

        self.alt_defter = ttk.Notebook(ust)
        self.alt_defter.pack(fill="both", expand=True)
        self.alt_defter.add(self._kayit_sekmesi(), text="  Çalışma kaydı  ")
        self.sorun_sekmesi = self._sorun_sekmesi()
        self.alt_defter.add(self.sorun_sekmesi, text="  Hatalar ve uyarılar (0)  ")
        self.sonuc_sekmesi = self._sonuc_sekmesi()
        self.alt_defter.add(self.sonuc_sekmesi, text="  Son çalışma: sonuçlar ve çıktılar  ")
        self._yaz(f"Web Denetim Merkezi {SURUM} hazır. Sol menüden bir sayfa açın; adımları seçip "
                  "'Seçilenleri çalıştır'a basın (Ctrl+Enter).\n")

    def _cubuklari_goster(self, goster):
        for etiket, cubuk, yuzde, satir in self.cubuk_satirlari:
            for w, kol, ek in ((etiket, 0, {}), (cubuk, 1, {"columnspan": 2}), (yuzde, 3, {})):
                if goster:
                    w.grid(row=satir, column=kol, sticky="we" if w is cubuk else "w",
                           pady=(8 if satir == 1 else 4, 0), padx=(0, 10) if w is not yuzde else 0, **ek)
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
        self.p = tema.uygula(self.kok, self.ayar["tema"])
        self._tema_renkleri()
        A.kaydet(self.ayar)
        self._durumu_yenile()

    def _tema_renkleri(self):
        p = self.p
        self._yan_boya()
        self.kayit.configure(background=p["konsol"], foreground=p["konsol_metin"],
                             insertbackground=p["konsol_metin"])
        self.kayit.tag_configure("hata", foreground="#ff7b72")
        self.kayit.tag_configure("uyari", foreground="#e3b341")
        for kc in KaydirmaliCerceve.hepsi:
            kc.renk(p["bg"])
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
            self._ana_sayfayi_doldur()

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
                  style="Soluk.TLabel", wraplength=520, justify="left").grid(row=7, column=0, columnspan=2,
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
            kimlik = A.yeni_profil(ad, url, degerler["site_adi"].get().strip())
            p.destroy()
            self.profil_secim.configure(values=A.profiller())
            self.profil_secim.set(kimlik)
            self._profil_degisti()
            self._sayfa_ac("ana")
            self._yaz("Yeni site hazır. Ana sayfadaki yol haritası sıradaki adımı gösterir "
                      "(önce site keşfi).\n")

        d = ttk.Frame(cer)
        d.grid(row=8, column=0, columnspan=2, sticky="e")
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
    def _secilenleri_calistir(self):
        if not self.secili:
            messagebox.showinfo("Seçim yok", "Adım listelerinde satırın başındaki kutuya tıklayarak "
                                             "çalıştırılacak adımları seçin.")
            return
        sira = [a.id for a in ADIMLAR if a.id in self.secili]   # programdaki doğal sıra
        self._baslat(sira)

    def _hat(self, ids, baslik="Hattı çalıştır"):
        adlar = "\n".join(f"  {i + 1}. {ADIM[a].ad}" for i, a in enumerate(ids))
        if messagebox.askyesno(baslik, f"Şu adımlar sırayla çalışacak:\n\n{adlar}\n\nBaşlatılsın mı?"):
            self._baslat(ids)

    def _baslat(self, ids):
        if self.calistirici.calisiyor or (self.is_parcacigi and self.is_parcacigi.is_alive()):
            messagebox.showinfo("Çalışıyor", "Önceki çalışma sürüyor. Bitmesini bekleyin veya durdurun.")
            return
        if not self._formu_oku():
            return
        adimlar = [ADIM[i] for i in ids]
        ayar = dict(self.ayar)   # çalışma sırasında form değişse de bu çalışma etkilenmesin
        self.durdur_dugmesi.configure(state="normal")
        self.calistir_dugmesi.configure(state="disabled")
        self.durum_cubugu.configure(text="Başlatılıyor…")
        self.calisma_bas = time.monotonic()
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
        devam = self.devam_var.get()

        def is_():
            tamam = self.calistirici.calistir(adimlar, ayar, devam_et=devam)
            self.kuyruk.put(("bitti", tamam, ayar))
        self.is_parcacigi = threading.Thread(target=is_, daemon=True)
        self.is_parcacigi.start()

    def _durdur(self):
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
        self.alt_defter.select(0)

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
        self._listeleri_yenile()
        if self.etkin_sayfa == "ana":
            self._ana_sayfayi_doldur()
        t = self.ozet_tablo
        t.delete(*t.get_children())
        bolumler = {}
        for bolum, baslik, deger in ozet(self.ayar):
            if bolum not in bolumler:
                bolumler[bolum] = t.insert("", "end", text=bolum, open=True)
            t.insert(bolumler[bolum], "end", text=baslik, values=(deger,))

    # ================================================================ kuyruk ve olaylar
    def _yaz_kuyruga(self, metin):
        self.kuyruk.put(("yaz", metin))

    def _olay_kuyruga(self, olay):
        self.kuyruk.put(("olay", olay))

    def _kuyrugu_bosalt(self):
        try:
            for _ in range(500):
                ileti = self.kuyruk.get_nowait()
                if ileti[0] == "yaz":
                    self._yaz(ileti[1])
                elif ileti[0] == "olay":
                    self._olay(ileti[1])
                elif ileti[0] == "ortam":
                    self._ortam_uyarisi(ileti[1])
                elif ileti[0] == "bitti":
                    _, tamam, ayar = ileti
                    if any(r["id"] in ("kurulum", "ortam") for r in self.calistirici.sonuclar):
                        threading.Thread(target=self._ortami_denetle, daemon=True).start()
                    if ayar.get("harita") != self.ayar.get("harita"):   # 'Keşif haritasını kullan'
                        self.ayar["harita"] = ayar["harita"]
                        self._formu_doldur()
                    self.durdur_dugmesi.configure(state="disabled")
                    self.calistir_dugmesi.configure(state="normal")
                    self.calisma_bas = None
                    self.kok.title(f"Web Denetim Merkezi {SURUM}")
                    self._durumu_yenile()
                    self.kok.bell()
        except queue.Empty:
            pass
        self.kok.after(100, self._kuyrugu_bosalt)

    def _olay(self, o):
        tur = o["tur"]
        if tur == "basladi":
            self.adim_sayisi = len(o["adimlar"])
        elif tur == "adim_basladi":
            self.durum_cubugu.configure(text=f"Adım {o['sira']}/{o['toplam']}  ·  {o['ad']}")
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
            self.kok.title(f"%{o['oran_genel'] * 100:.0f} · Web Denetim Merkezi")
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
        """Çalışırken geçen süreyi her saniye günceller (ilerleme satırı gelmese de)."""
        if self.calisma_bas is None:
            return
        self.gecen_etiketi.configure(text=f"Geçen {sure_metni(time.monotonic() - self.calisma_bas)}")
        self.kok.after(1000, self._saat)

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
        n = len(self.sorun_tablo.get_children())
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
        self.alt_defter.select(0)
        self.kayit.tag_remove("vurgu", "1.0", "end")
        self.kayit.tag_add("vurgu", f"{isaret} linestart", f"{isaret} lineend+1c")
        self.kayit.see(isaret)

    def _sorunlari_temizle(self):
        self.sorun_tablo.delete(*self.sorun_tablo.get_children())
        self.sorun_isaretleri.clear()
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
    def _sonuclari_goster(self, sonuclar, tamam):
        t = self.sonuc_tablo
        t.delete(*t.get_children())
        self.sonuc_yollari = {}       # tablo satırı -> tam dosya yolu
        for r in sonuclar:
            ust = t.insert("", "end", text=r["ad"], open=True, tags=(r["sonuc"],), values=(
                DURUM_YAZI[r["sonuc"]], sure_metni(r["sure_sn"]), f"{r['hata']} / {r['uyari']}", ""))
            for yol in r["ciktilar"]:
                oge = t.insert(ust, "end", text="    " + Path(yol).name, values=("çıktı", "", "", _kisa_yol(yol)))
                self.sonuc_yollari[oge] = yol
            if r["kayit"]:
                oge = t.insert(ust, "end", text="    Çalışma kaydı", values=("kayıt", "", "", _kisa_yol(r["kayit"])))
                self.sonuc_yollari[oge] = r["kayit"]
        basarili = sum(r["sonuc"] == "basarili" for r in sonuclar)
        hata = sum(r["hata"] for r in sonuclar)
        uyari = sum(r["uyari"] for r in sonuclar)
        toplam_sure = sum(r["sure_sn"] for r in sonuclar)
        ozet_metni = (f"{len(sonuclar)} adımdan {basarili} başarılı · {hata} hata, {uyari} uyarı · "
                      f"toplam {sure_metni(toplam_sure)}")
        self.sonuc_ozet.configure(text=ozet_metni,
                                  style="Kalin.TLabel" if tamam else "Hata.TLabel")
        self.durum_cubugu.configure(text=("✔ Bitti  ·  " if tamam else "✖ Bitti (hata veya durdurma var)  ·  ")
                                    + ozet_metni)
        calisan = len(sonuclar) / max(self.adim_sayisi or len(sonuclar), 1)
        self.genel_cubugu["value"] = calisan * 1000
        self.genel_yuzde.configure(text=f"%{calisan * 100:.0f} · " + (
            "tamamlandı" if tamam else f"{len(sonuclar)} adım çalıştı, {len(sonuclar) - basarili} sorunlu"))
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
