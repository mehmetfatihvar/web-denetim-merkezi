"""Araç çıktısından ilerleme, kalan süre ve hata/uyarı çıkarma (arayüzden bağımsız).

Araçlar ilerlemeyi farklı biçimlerde basar; hepsi burada tanınır:
  tester, doğrulama, metin, tarama, analiz, yerel model : "[12/2000] ..."
  link/belge alt aşamaları                             : "    120/900 (3 kırık)"
  keşif                                                : "450 sayfa | kuyruk 1200 | ..."
  Bologna (slog)                                       : "ilerleme biten=12 toplam=442 ..."
"""

import re
import time
from collections import deque
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
    """Oran (0-1) gözlemlerinden kalan süre.

    Hız, son `pencere` saniyedeki ilerlemeden ölçülür (kayan pencere): sunucu yavaşlayıp
    hızlandıkça tahmin de güncellenir, baştaki tarayıcı açılışı gibi geçici durumlar
    tahmini sonsuza dek etkilemez.

    Gerçek iş sayılmayan sıçramalar hıza katılmaz: `atlama=True` ile bildirilen artış
    (ör. tam testte zaten yapılmış olduğu için saniyede geçen bir parça) kalan işi azaltır
    ama "bu hızla gidiyoruz" hesabına girmez. Geri giden oran yok sayılır.
    """

    def __init__(self, simdi=time.monotonic, pencere: float = 600.0):
        self.simdi = simdi
        self.pencere = pencere
        self.son = 0.0                  # en yüksek oran (geri gitmez)
        self.islenen = 0.0              # gerçekten çalışılarak yapılan toplam ilerleme
        self.gozlem = deque()           # (zaman, islenen)

    def ekle(self, oran: float, atlama: bool = False):
        t = self.simdi()
        artis = max(0.0, oran - self.son)
        self.son = max(self.son, oran)
        if not atlama:
            self.islenen += artis
        self.gozlem.append((t, self.islenen))
        # pencerenin başını belirleyen bir gözlem hep kalsın
        while len(self.gozlem) > 2 and self.gozlem[1][0] <= t - self.pencere:
            self.gozlem.popleft()

    def kalan(self) -> Optional[float]:
        if not self.gozlem:
            return None
        t0, i0 = self.gozlem[0]
        gecen = self.simdi() - t0       # şu ana kadar: ilerleme durduysa tahmin uzar
        ilerleme = self.islenen - i0
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
