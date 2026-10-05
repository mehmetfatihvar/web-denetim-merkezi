"""Kılavuzdaki adım ve ayar tablolarının kaynağı: programın kendi tanımlarından veri.json üretir.
Böylece kılavuz, programa adım ya da ayar eklendiğinde elle güncellenmeden doğru kalır."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from merkez import arayuz  # noqa: E402  (ayar formu tanımları; tkinter gerekir)
from merkez.adimlar import ADIMLAR, AI_HATTI, GRUPLAR, TAM_HAT  # noqa: E402
from merkez.ayarlar import VARSAYILAN  # noqa: E402


def bolumler(liste):
    return [[b, [[k, e, t, y, VARSAYILAN.get(k)] for k, e, t, y, _ in alanlar]] for b, alanlar in liste]


veri = {
    "gruplar": GRUPLAR,
    "adimlar": [{"id": a.id, "grup": a.grup, "ad": a.ad, "aciklama": a.aciklama, "sure": a.sure} for a in ADIMLAR],
    "tam_hat": TAM_HAT, "ai_hatti": AI_HATTI,
    "ayarlar": {"site": bolumler(arayuz.SITE_ALANLARI), "genel": bolumler(arayuz.GENEL_ALANLARI)},
}
hedef = Path(__file__).with_name("veri.json")
hedef.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{hedef}: {len(veri['adimlar'])} adım")
