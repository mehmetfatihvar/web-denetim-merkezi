"""Arayüz teması: açık/karanlık, renk paleti ve özel stiller.

`sv-ttk` (Windows 11 "Sun Valley" görünümü) kuruluysa o kullanılır. Kurulu değilse
yerleşik 'clam' teması aynı renk paletiyle boyanır; program her durumda çalışır.
"""

import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

try:
    import sv_ttk
except ImportError:  # isteğe bağlı bağımlılık
    sv_ttk = None

PALET = {
    "light": {
        "bg": "#fafafa", "yan": "#f0f2f5", "kart": "#ffffff", "kenar": "#e1e4e8",
        "metin": "#1b1f24", "soluk": "#5b6475", "vurgu": "#005fb8", "vurgu_metin": "#ffffff",
        "secili": "#dce9f9", "basari": "#1a7f37", "hata": "#cf222e", "uyari": "#9a6700",
        "bilgi": "#0b57d0", "konsol": "#0f1419", "konsol_metin": "#d6dde6",
    },
    "dark": {
        "bg": "#1c1c1c", "yan": "#202020", "kart": "#2b2b2b", "kenar": "#3a3a3a",
        "metin": "#f3f3f3", "soluk": "#a0a7b4", "vurgu": "#57c8ff", "vurgu_metin": "#000000",
        "secili": "#2f4a63", "basari": "#56d364", "hata": "#ff7b72", "uyari": "#e3b341",
        "bilgi": "#79c0ff", "konsol": "#0d1117", "konsol_metin": "#d6dde6",
    },
}


def yazi_ailesi():
    aileler = set(tkfont.families())
    for ad in ("Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter",
               "Noto Sans", "DejaVu Sans"):
        if ad in aileler:
            return ad
    return "TkDefaultFont"


def konsol_yazisi():
    aileler = set(tkfont.families())
    for ad in ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono"):
        if ad in aileler:
            return ad
    return "TkFixedFont"


def uygula(kok: tk.Tk, ad: str, hizli: bool = False) -> dict:
    """Temayı uygular, paleti döndürür.

    hizli=True: sv-ttk yerine yerleşik 'clam' teması. sv-ttk her öğeyi resimlerle çizer;
    bazı Windows bilgisayarlarda (özellikle yüksek ölçeklemede) sayfa geçişi ve pencere
    boyutlandırma bu yüzden kasar. Sade görünüm aynı renklerle yaklaşık iki kat hızlı çizer.
    """
    ad = "dark" if ad == "dark" else "light"
    p = PALET[ad]
    s = ttk.Style(kok)
    if sv_ttk is not None and not hizli:
        sv_ttk.set_theme(ad)
    else:
        _clam_boya(s, p)
    aile = yazi_ailesi()
    for ad_, boyut in (("TkDefaultFont", 10), ("TkTextFont", 10), ("TkHeadingFont", 10),
                       ("TkMenuFont", 10)):
        try:
            tkfont.nametofont(ad_).configure(family=aile, size=boyut)
        except tk.TclError:
            pass
    kok.configure(background=p["bg"])

    s.configure("Baslik.TLabel", font=(aile, 17, "bold"), foreground=p["metin"])
    s.configure("AltBaslik.TLabel", font=(aile, 12, "bold"), foreground=p["metin"])
    s.configure("Kalin.TLabel", font=(aile, 10, "bold"))
    s.configure("Soluk.TLabel", foreground=p["soluk"])
    s.configure("Basari.TLabel", foreground=p["basari"])
    s.configure("Hata.TLabel", foreground=p["hata"], font=(aile, 10, "bold"))
    s.configure("Uyari.TLabel", foreground=p["uyari"], font=(aile, 10, "bold"))
    s.configure("Yuzde.TLabel", font=(aile, 10, "bold"))
    s.configure("Sayi.TLabel", font=(aile, 20, "bold"), foreground=p["metin"])
    s.configure("SayiVurgu.TLabel", font=(aile, 20, "bold"), foreground=p["vurgu"])
    s.configure("SayiHata.TLabel", font=(aile, 20, "bold"), foreground=p["hata"])
    s.configure("Treeview", rowheight=30)
    s.configure("Ilerleme.Horizontal.TProgressbar", thickness=8)
    s.configure("Vurgu.TLabel", foreground=p["vurgu"], font=(aile, 10, "bold"))
    s.configure("Canli.TLabel", foreground=p["vurgu"], font=(aile, 15, "bold"))
    s.configure("CanliUyari.TLabel", foreground=p["uyari"], font=(aile, 15, "bold"))
    s.configure("CanliBasari.TLabel", foreground=p["basari"], font=(aile, 15, "bold"))
    s.configure("CanliHata.TLabel", foreground=p["hata"], font=(aile, 15, "bold"))
    s.configure("Buyuk.TLabel", font=(aile, 13, "bold"), foreground=p["metin"])
    s.configure("Buyuk.Accent.TButton", font=(aile, 11, "bold"), padding=(18, 8))
    return p


_ONAY_RESIMLERI = {}   # kök pencere -> (boş, işaretli, üzerinde): tema değişince yerinde boyanır


def _karistir(a: str, b: str, oran: float) -> str:
    oran = min(max(oran, 0.0), 1.0)
    ra, ga, ba = (int(a[i:i + 2], 16) for i in (1, 3, 5))
    rb, gb, bb = (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * oran), round(ga + (gb - ga) * oran),
                              round(ba + (bb - ba) * oran))


def _onay_boya(resim: tk.PhotoImage, n: int, zemin: str, kenar: str, isaret: str = None):
    """n×n kutu (1 px kenar); isaret verilirse içine yumuşak kenarlı ✓ çizer."""
    t = max(1.6, n / 7)                                  # çizgi kalınlığı
    noktalar = [(0.24 * n, 0.53 * n), (0.43 * n, 0.71 * n), (0.77 * n, 0.31 * n)]

    def uzaklik(x, y):
        en = 1e9
        for (x1, y1), (x2, y2) in zip(noktalar, noktalar[1:]):
            dx, dy = x2 - x1, y2 - y1
            k = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            en = min(en, ((x - x1 - k * dx) ** 2 + (y - y1 - k * dy) ** 2) ** 0.5)
        return en

    satirlar = []
    for y in range(n):
        satir = []
        for x in range(n):
            if x in (0, n - 1) or y in (0, n - 1):
                renk = kenar
            elif isaret:
                renk = _karistir(zemin, isaret, t / 2 + 0.5 - uzaklik(x + 0.5, y + 0.5))
            else:
                renk = zemin
            satir.append(renk)
        satirlar.append("{" + " ".join(satir) + "}")
    resim.put(" ".join(satirlar), to=(0, 0))


def _onay_kutusu(s: ttk.Style, p: dict):
    """clam'in çarpılı (☒) kutusu yerine işaretliyken vurgu renginde ✓; ölçeklemeye göre boyutlanır."""
    kok = s.master
    if kok not in _ONAY_RESIMLERI:
        n = max(13, round(tkfont.nametofont("TkDefaultFont").metrics("linespace") * 0.8))
        resimler = tuple(tk.PhotoImage(master=kok, width=n + 7, height=n) for _ in range(3))  # sağ 7 px boşluk
        _ONAY_RESIMLERI[kok] = (n, resimler)
        bos, isaretli, uzerinde = resimler
        try:
            s.element_create("Onay.indicator", "image", bos, ("selected", isaretli),
                             ("active", uzerinde), sticky="w")
        except tk.TclError:
            pass
    n, (bos, isaretli, uzerinde) = _ONAY_RESIMLERI[kok]
    _onay_boya(bos, n, p["kart"], p["soluk"])
    _onay_boya(uzerinde, n, p["secili"], p["vurgu"])
    _onay_boya(isaretli, n, p["vurgu"], p["vurgu"], p["vurgu_metin"])
    s.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("Onay.indicator", {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})])


def _clam_boya(s: ttk.Style, p: dict):
    """sv-ttk yokken: clam temasını aynı paletle boya ve sv-ttk stil adlarını tanımla."""
    s.theme_use("clam")
    s.configure(".", background=p["bg"], foreground=p["metin"], fieldbackground=p["kart"],
                bordercolor=p["kenar"], lightcolor=p["kenar"], darkcolor=p["kenar"],
                troughcolor=p["kenar"], selectbackground=p["secili"], selectforeground=p["metin"],
                insertcolor=p["metin"])
    # Düz (flat) düğmeler: clam'in kabartma gölgeleri zeminle aynı renge çekilir
    s.configure("TButton", padding=(12, 5), width=0, background=p["kart"], bordercolor=p["kenar"],
                lightcolor=p["kart"], darkcolor=p["kart"], focuscolor=p["vurgu"])
    s.map("TButton", background=[("disabled", p["bg"]), ("pressed", p["kenar"]), ("active", p["secili"])],
          lightcolor=[("disabled", p["bg"]), ("pressed", p["kenar"]), ("active", p["secili"])],
          darkcolor=[("disabled", p["bg"]), ("pressed", p["kenar"]), ("active", p["secili"])],
          foreground=[("disabled", p["soluk"])])
    s.configure("Accent.TButton", background=p["vurgu"], foreground=p["vurgu_metin"],
                bordercolor=p["vurgu"], lightcolor=p["vurgu"], darkcolor=p["vurgu"])
    s.map("Accent.TButton", background=[("disabled", p["kenar"]), ("active", p["bilgi"])],
          lightcolor=[("disabled", p["kenar"]), ("active", p["bilgi"])],
          darkcolor=[("disabled", p["kenar"]), ("active", p["bilgi"])],
          bordercolor=[("disabled", p["kenar"]), ("active", p["bilgi"])])
    # Onay kutusu: seçiliyken vurgu rengiyle dolu kutu
    s.configure("TCheckbutton", background=p["bg"], indicatorbackground=p["kart"],
                indicatorforeground=p["vurgu_metin"], indicatormargin=(0, 0, 6, 0),
                bordercolor=p["soluk"], lightcolor=p["kart"], darkcolor=p["kart"])
    s.map("TCheckbutton", background=[("active", p["bg"])],
          indicatorbackground=[("selected", p["vurgu"]), ("active", p["secili"])])
    _onay_kutusu(s, p)
    # İnce, düz kaydırma çubukları
    for yon in ("Vertical", "Horizontal"):
        s.configure(f"{yon}.TScrollbar", background=p["kenar"], troughcolor=p["bg"],
                    bordercolor=p["bg"], lightcolor=p["kenar"], darkcolor=p["kenar"],
                    arrowcolor=p["soluk"], gripcount=0, arrowsize=12, relief="flat")
        s.map(f"{yon}.TScrollbar", background=[("active", p["soluk"])],
              lightcolor=[("active", p["soluk"])], darkcolor=[("active", p["soluk"])])
    s.configure("Horizontal.TProgressbar", background=p["vurgu"], troughcolor=p["kenar"],
                bordercolor=p["kenar"], lightcolor=p["vurgu"], darkcolor=p["vurgu"])
    s.configure("TCombobox", arrowcolor=p["soluk"], background=p["kart"], lightcolor=p["kart"],
                darkcolor=p["kart"], selectbackground=p["kart"], selectforeground=p["metin"])
    s.map("TCombobox", fieldbackground=[("readonly", p["kart"])], background=[("active", p["secili"])])
    s.configure("TPanedwindow", background=p["bg"])
    s.configure("Sash", sashthickness=6, gripcount=0, background=p["bg"], lightcolor=p["bg"],
                darkcolor=p["bg"], bordercolor=p["bg"])
    # Kart zemini pencereyle aynı: ttk etiketleri kendi zeminlerini kartın rengine uyduramaz
    s.configure("Card.TFrame", background=p["bg"], relief="solid", borderwidth=1)
    s.configure("TEntry", fieldbackground=p["kart"], padding=4)
    s.configure("TCombobox", fieldbackground=p["kart"], padding=3)
    s.configure("TNotebook.Tab", bordercolor=p["kenar"], lightcolor=p["bg"], darkcolor=p["bg"])
    s.configure("Treeview", background=p["kart"], fieldbackground=p["kart"], foreground=p["metin"])
    s.configure("Treeview.Heading", background=p["bg"], foreground=p["soluk"], relief="flat")
    s.map("Treeview", background=[("selected", p["secili"])], foreground=[("selected", p["metin"])])
    s.configure("TNotebook", background=p["bg"], borderwidth=0)
    s.configure("TNotebook.Tab", padding=(12, 5), background=p["bg"])
    s.map("TNotebook.Tab", background=[("selected", p["kart"])], lightcolor=[("selected", p["kart"])])
    s.configure("TLabelframe", background=p["bg"])
    s.configure("TLabelframe.Label", background=p["bg"], foreground=p["metin"])
    for ad in ("Switch.TCheckbutton", "Toggle.TButton"):
        temel = ad.split(".", 1)[1]
        try:
            s.layout(ad, s.layout(temel))
        except tk.TclError:
            pass


def windows_basligi(kok: tk.Tk, karanlik: bool):
    """Windows 10/11'de pencere başlık çubuğunu temayla uyumlu yap (başka sistemde yok sayılır)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kok.update()
        hwnd = ctypes.windll.user32.GetParent(kok.winfo_id())
        deger = ctypes.c_int(1 if karanlik else 0)
        for nitelik in (20, 19):    # DWMWA_USE_IMMERSIVE_DARK_MODE (yeni ve eski numara)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, nitelik, ctypes.byref(deger),
                                                           ctypes.sizeof(deger)) == 0:
                break
    except Exception:
        pass


def sv_ttk_var() -> bool:
    return sv_ttk is not None

