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
    return p


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

