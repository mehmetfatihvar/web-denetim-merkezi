"""
Önerilen CSS düzeltmesinin etkisini ölçer.

1) hazirla    : doğrulama çekiminde yana kayan sayfaları seçer
     python css_deneme.py hazirla
   -> css_cikti/css_urls.json

2) Seçilen sayfalar CSS eklenerek yeniden çekilir:
     python ..\\cekim\\tester.py --source css_cikti\\css_urls.json --out-dir ..\\dogrulama_css ^
            --check-visual --kaydir --fresh --css oneri.css

3) karsilastir: aynı sayfaların CSS'siz ve CSS'li ölçümünü karşılaştırır
     python css_deneme.py karsilastir
   -> css_cikti/css_sonuc.csv, css_ozet.txt
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

CIHAZLAR = ("mobile", "desktop")


def olcumler(yol):
    if not Path(yol).exists():
        sys.exit(f"[HATA] {yol} yok.")
    olcum = {}
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            try:
                r = json.loads(satir)
            except ValueError:
                continue
            olcum[r["url"]] = (r.get("visual") or {}).get("sayfa_genislik") or {}
    return olcum


def hazirla(a):
    once = olcumler(Path(a.once) / "results.jsonl")
    urls = [u for u, g in once.items() if any((g.get(c) or {}).get("kayiyor") for c in CIHAZLAR)]
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    with open(cikti / "css_urls.json", "w", encoding="utf-8") as f:
        json.dump({"url_list": urls}, f, ensure_ascii=False, indent=1)
    print(f"✅ {len(urls)} yana kayan sayfa -> {cikti / 'css_urls.json'}")


def karsilastir(a):
    once = olcumler(Path(a.once) / "results.jsonl")
    sonra = olcumler(Path(a.sonra) / "results.jsonl")
    satirlar, durum = [], defaultdict(Counter)
    kalan_neden = Counter()
    for url, g2 in sonra.items():
        g1 = once.get(url)
        if g1 is None:
            continue
        for c in CIHAZLAR:
            o, s = g1.get(c) or {}, g2.get(c) or {}
            if not o or not s:
                continue
            k1, k2 = bool(o.get("kayiyor")), bool(s.get("kayiyor"))
            if not k1 and not k2:
                continue
            d = {(True, False): "DUZELDI", (True, True): "KALDI", (False, True): "YENI_BOZULDU"}[(k1, k2)]
            durum[c][d] += 1
            t = s.get("tasiran") or {}
            if d != "DUZELDI" and t.get("selector"):
                kalan_neden[(c, t["selector"], t.get("ws", "?"), "prose" if t.get("prose") else "prose-dışı",
                             t.get("ata", ""))] += 1
            satirlar.append({
                "durum": d, "cihaz": c, "url": url,
                "once_tasma_px": max(0, (o.get("scroll") or 0) - (o.get("client") or 0)),
                "sonra_tasma_px": max(0, (s.get("scroll") or 0) - (s.get("client") or 0)),
                "kalan_oge": t.get("selector", ""), "kalan_metin": t.get("metin", ""),
                "white_space": t.get("ws", ""), "display": t.get("display", ""),
                "icerik_alani": ("evet" if t.get("prose") else "hayir") if t else "",
                "ata": t.get("ata", ""),
            })

    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    alanlar = ["durum", "cihaz", "url", "once_tasma_px", "sonra_tasma_px", "kalan_oge", "kalan_metin",
               "white_space", "display", "icerik_alani", "ata"]
    with open(cikti / "css_sonuc.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=alanlar, delimiter=";")
        w.writeheader()
        w.writerows(sorted(satirlar, key=lambda r: (r["durum"], r["cihaz"], r["url"])))

    L = ["=" * 64, "CSS DÜZELTME DENEMESİ (önce: CSS'siz, sonra: oneri.css ekli)", "=" * 64, ""]
    for c in CIHAZLAR:
        n = durum[c]
        once_kayan = n["DUZELDI"] + n["KALDI"]
        if not once_kayan and not n["YENI_BOZULDU"]:
            continue
        oran = f"{n['DUZELDI'] / once_kayan:.0%}" if once_kayan else "-"
        L.append(f"{c:8s} yana kayan {once_kayan:4d} sayfa -> düzeldi {n['DUZELDI']:4d} ({oran}), "
                 f"kaldı {n['KALDI']:4d}, yeni bozulan {n['YENI_BOZULDU']:3d}")
    if kalan_neden:
        L += ["", "Hâlâ kayan sayfalarda sayfayı genişleten öğe (white-space, konum, üst öğe):"]
        L += [f"  {adet:4d} sayfa  {c:8s} {sel}  [{ws}, {yer}]  {ata[:50]}"
              for (c, sel, ws, yer, ata), adet in kalan_neden.most_common(15)]
    L += ["", "Not: 'yeni bozulan' > 0 ise CSS başka bir yeri bozmuş olabilir; o sayfaların",
          "ekran görüntülerini (..\\dogrulama_css\\screenshots) elle kontrol edin."]
    metin = "\n".join(L)
    print(metin)
    (cikti / "css_ozet.txt").write_text(metin + "\n", encoding="utf-8")
    print(f"\n💾 {cikti / 'css_sonuc.csv'}, css_ozet.txt")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = ap.add_subparsers(dest="komut", required=True)
    h = alt.add_parser("hazirla")
    k = alt.add_parser("karsilastir")
    for s in (h, k):
        s.add_argument("--once", default="../dogrulama", help="CSS'siz çekimin --out-dir klasörü")
        s.add_argument("--cikti", default="css_cikti")
    k.add_argument("--sonra", default="../dogrulama_css", help="CSS'li çekimin --out-dir klasörü")
    a = ap.parse_args()
    {"hazirla": hazirla, "karsilastir": karsilastir}[a.komut](a)


if __name__ == "__main__":
    main()
