#!/usr/bin/env python3
"""
Temsilci sayfaların URL listesini çıkarır (yeniden çekim için).

tarama.py'nin seçtiği temsilci görüntüler (ornekler.csv) dosya adıyla tutulur.
Dosya adları cekim/tester.py'deki safe_name() ile URL'den üretilir
(yol + md5(url)[:8]). Bu script site haritasındaki her URL için aynı adı
hesaplayıp eşleştirir ve tester'ın --source ile okuyabileceği bir JSON yazar.

Kullanım:
  python temsilci_urls.py --harita ..\\data\\final_complete_site_map.json
  python ..\\cekim\\tester.py --source temsilci_urls.json --out-dir ..\\yeniden_cekim --kaydir

Çıktı: temsilci_urls.json  {"url_list": [...]}  + eşleşmeyenlerin listesi
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def safe_name(url, maxlen=110):
    """cekim/tester.py safe_name ile birebir aynı olmalı."""
    p = urlparse(url)
    path = (p.path or "/").strip("/")
    q = ("_" + re.sub(r"[^a-zA-Z0-9]+", "-", p.query)) if p.query else ""
    name = re.sub(r"[^a-zA-Z0-9]+", "-", path) + q
    name = name.strip("-") or "anasayfa"
    if len(name) > maxlen:
        name = name[:maxlen]
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return f"{name}-{digest}"


def harita_urlleri(yol):
    with open(yol, encoding="utf-8") as f:
        veri = json.load(f)
    if isinstance(veri, dict):
        for anahtar in ("url_list", "urls"):
            if anahtar in veri:
                return list(veri[anahtar])
        if "pages" in veri:
            return list(veri["pages"].keys())
    if isinstance(veri, list):
        return [x["url"] if isinstance(x, dict) else x for x in veri]
    return list(veri)


def main():
    p = argparse.ArgumentParser(description="Temsilci sayfaların URL listesini çıkar")
    p.add_argument("--ornekler", default="denetim_cikti/ornekler.csv")
    p.add_argument("--harita", required=True, help="final_complete_site_map.json yolu")
    p.add_argument("--cikti", default="temsilci_urls.json")
    a = p.parse_args()

    ad_url = {}
    for u in harita_urlleri(a.harita):
        if isinstance(u, str) and u.startswith("http"):
            ad_url.setdefault(safe_name(u), u)

    with open(a.ornekler, encoding="utf-8-sig", newline="") as f:
        sayfalar = list(dict.fromkeys(r["sayfa"] for r in csv.DictReader(f, delimiter=";")))

    bulunan, eksik = [], []
    for s in sayfalar:
        (bulunan if s in ad_url else eksik).append(s)
    urls = [ad_url[s] for s in bulunan]

    Path(a.cikti).write_text(json.dumps({"url_list": urls}, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print(f"✅ {len(sayfalar)} temsilci sayfanın {len(bulunan)} tanesinin URL'si bulundu "
          f"-> {a.cikti}")
    if eksik:
        eksik_yol = Path(a.cikti).with_suffix(".eksik.txt")
        eksik_yol.write_text("\n".join(eksik), encoding="utf-8")
        print(f"⚠️  {len(eksik)} sayfa haritada bulunamadı -> {eksik_yol} "
              "(tester başka bir URL kaynağıyla çalıştırılmış olabilir)")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
