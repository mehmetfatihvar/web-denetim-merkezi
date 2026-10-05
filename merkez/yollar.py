"""Repo içindeki sabit klasörler. Program repo kökünden çalışır; repo nereye
kopyalanırsa kopyalansın yollar buna göre çözülür."""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROGRAM = REPO
ARACLAR = REPO / "tools"
GORSEL_DENETIM = ARACLAR / "visual_audit"
VERI = REPO / "data"
BOLOGNA = REPO / "bologna-scraper"
CIKTILAR = REPO / "ciktilar"
AYAR_DOSYASI = REPO / "ayarlar.json"
PROFILLER = REPO / "profiller"
