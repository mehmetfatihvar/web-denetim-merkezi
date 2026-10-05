"""Araç çıktısından ilerleme, kalan süre ve hata/uyarı çıkarma (arayüzden bağımsız).

Araçlar ilerlemeyi farklı biçimlerde basar; hepsi burada tanınır:
  tester, doğrulama, metin, tarama, analiz, yerel model : "[12/2000] ..."
  link/belge alt aşamaları                             : "    120/900 (3 kırık)"
  keşif                                                : "450 sayfa | kuyruk 1200 | ..."
  Bologna (slog)                                       : "ilerleme biten=12 toplam=442 ..."
"""

import re
import time
from typing import Optional, Tuple

ILERLEME_DESENLERI = [
    # (desen, toplam nasıl hesaplanır)
    (re.compile(r"\bbiten(?:_kod)?=(\d+)\s+toplam(?:_kod)?=(\d+)"), "toplam"),
    (re.compile(r"\[(\d+)\s*/\s*(\d+)\]"), "toplam"),
    (re.compile(r"\b(\d+) sayfa \| kuyruk (\d+)\b"), "kuyruk"),
    (re.compile(r"^\s+(\d+)\s*/\s*(\d+)(?:\s|$)"), "toplam"),
]

HATA_DESENLERI = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"^\s*[\w.]*(?:Error|Exception)(?::|$)"),     # Python istisna son satırı
    re.compile(r"\[HATA\]|^\s*HATA\s*:|❌|⛔|✖"),      # "HATA TÜRÜ" gibi başlıklar sayılmaz
    re.compile(r"\blevel=ERROR\b"),
    re.compile(r"^(?:error|fatal|panic)\b[:\s]", re.IGNORECASE),
    re.compile(r"\bno space left on device\b", re.IGNORECASE),
]
UYARI_DESENLERI = [
    re.compile(r"\[!\]|\bUYARI\b|\bUyarı\b|⚠"),
    re.compile(r"\blevel=WARN\b"),
    re.compile(r"\bWARNING\b|\bWarning:"),
    re.compile(r"\[\d+/\d+\]\s+ERROR\b"),     # tester: sayfa açılamadı / zaman aşımı
]


def ilerleme_oku(satir: str) -> Optional[Tuple[int, int]]:
    """Satırda ilerleme bilgisi varsa (biten, toplam)."""
    for desen, tur in ILERLEME_DESENLERI:
        m = desen.search(satir)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        toplam = a + b if tur == "kuyruk" else b
        if toplam > 0 and a <= toplam:
            return a, toplam
    return None


def sorun_turu(satir: str) -> Optional[str]:
    """'hata', 'uyari' veya None."""
    if not satir.strip():
        return None
    for d in HATA_DESENLERI:
        if d.search(satir):
            return "hata"
    for d in UYARI_DESENLERI:
        if d.search(satir):
            return "uyari"
    return None


class SatirBolucu:
    """Parça parça gelen çıktıyı satırlara böler (\\n ve \\r ikisi de satır sonu)."""

    def __init__(self):
        self.tampon = ""

    def ekle(self, metin: str):
        self.tampon += metin
        parcalar = re.split(r"\r\n|\r|\n", self.tampon)
        self.tampon = parcalar.pop()
        return parcalar

    def bitir(self):
        kalan, self.tampon = self.tampon, ""
        return [kalan] if kalan else []


class SureTahmini:
    """Oran (0-1) gözlemlerinden kalan süre. Hız, ilk gözlemden bu yana ortalamadır;
    devam eden işlerde atlanan (hızlı geçen) kısım tahmini bozmasın diye ilk gözlemden
    itibaren ölçülür."""

    def __init__(self, simdi=time.monotonic):
        self.simdi = simdi
        self.t0 = None
        self.o0 = 0.0
        self.son = 0.0

    def ekle(self, oran: float):
        t = self.simdi()
        if self.t0 is None or oran < self.son:
            self.t0, self.o0 = t, oran
        self.son = oran

    def kalan(self) -> Optional[float]:
        if self.t0 is None:
            return None
        gecen = self.simdi() - self.t0
        ilerleme = self.son - self.o0
        if gecen < 5 or ilerleme <= 0:
            return None
        return (1.0 - self.son) * gecen / ilerleme


def sure_metni(sn) -> str:
    if sn is None:
        return "hesaplanıyor"
    sn = int(sn)
    if sn < 60:
        return f"{sn} sn"
    if sn < 3600:
        return f"{sn // 60} dk {sn % 60:02d} sn"
    return f"{sn // 3600} sa {sn % 3600 // 60:02d} dk"
