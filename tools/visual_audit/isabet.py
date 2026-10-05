#!/usr/bin/env python3
"""
Görsel Denetim - Aşama 3: Yapay zeka bulgularının isabet ölçümü

analiz.py sonuçlarından (sonuclar.jsonl) üç ölçüm çıkarır:

  1. Hata türü başına isabet: ana modelin (ör. Gemma) bulduğu her (cihaz, tür) için
     hakeme rastgele örnek gönderildiyse, hakemin aynı türü aynı dilimde kaç kez
     onayladığı (--hakem-grup tur ile çalıştırılan hakem turu).
  2. Taşma bulgusu - kod ölçümü karşılaştırması: tarama.csv'deki piksel ölçümüyle
     bulunan gerçek yatay taşma (TASMA bayrağı) referans alınarak ana modelin
     horizontal_overflow bulgularının isabet (precision) ve yakalama (recall) oranı.
  3. Mojibake bulgularının kanıt metinleri (elle kontrol için): tester sayfa
     metinlerinde mojibake ölçmediği için bu bulgular şüphelidir.

Kullanım:
  python isabet.py --cikti denetim_cikti/ai_v2 --ana gemini:gemma-4-31b-it \\
                   --hakem gemini:gemini-3.5-flash-lite --tarama denetim_cikti/tarama.csv

Çıktı: <cikti>/isabet.txt ve isabet.csv
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def kayitlari_oku(yol):
    son = {}
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            try:
                r = json.loads(satir)
            except json.JSONDecodeError:
                continue
            k = (r["model"], r["dosya"], r["dilim"])
            if not r.get("hata") or k not in son:
                son[k] = r
    return [r for r in son.values() if not r.get("hata") and r.get("cevap")]


def main():
    p = argparse.ArgumentParser(description="Yapay zeka bulgularının isabet ölçümü")
    p.add_argument("--cikti", default="denetim_cikti/ai_v2")
    p.add_argument("--ana", default="gemini:gemma-4-31b-it", help="Ana tarama modeli")
    p.add_argument("--hakem", default="gemini:gemini-3.5-flash-lite", help="Hakem modeli")
    p.add_argument("--tarama", default="denetim_cikti/tarama.csv",
                   help="tarama.py çıktısı (piksel ölçümüyle TASMA bayrakları)")
    a = p.parse_args()

    cikti = Path(a.cikti)
    kayitlar = kayitlari_oku(cikti / "sonuclar.jsonl")
    ana = {(r["dosya"], r["dilim"]): r for r in kayitlar if r["model"] == a.ana}
    hakem = {(r["dosya"], r["dilim"]): r for r in kayitlar if r["model"] == a.hakem}
    turler = lambda r: {d.get("type") for d in r["cevap"].get("defects", [])}

    L = ["=" * 72, "GÖRSEL DENETİM - YAPAY ZEKA İSABET ÖLÇÜMÜ", "=" * 72, "",
         f"Ana model  : {a.ana}  ({len(ana)} dilim)",
         f"Hakem model: {a.hakem}  ({len(hakem)} dilim)", ""]

    # 1) Hata türü başına isabet (hakem örneklemi üzerinden)
    say = defaultdict(lambda: {"ana": 0, "ornek": 0, "onay": 0})
    for k, r in ana.items():
        for tur in turler(r):
            g = say[(r["cihaz"], tur)]
            g["ana"] += 1
            if k in hakem:
                g["ornek"] += 1
                g["onay"] += tur in turler(hakem[k])
    satirlar = []
    L.append("1) HATA TÜRÜ BAŞINA İSABET (hakem aynı dilimde aynı türü buldu mu?)")
    L.append(f"   {'cihaz':8s} {'tür':22s} {'ana bulgu':>9s} {'örnek':>6s} {'onay':>5s} {'isabet':>7s}")
    for (cihaz, tur), g in sorted(say.items(), key=lambda x: (-x[1]["ana"], x[0])):
        isabet = g["onay"] / g["ornek"] if g["ornek"] else None
        satirlar.append({"cihaz": cihaz, "tur": tur, "ana_bulgu": g["ana"], "ornek": g["ornek"],
                         "onay": g["onay"],
                         "isabet": f"{isabet:.0%}" if isabet is not None else ""})
        L.append(f"   {cihaz:8s} {tur:22s} {g['ana']:9d} {g['ornek']:6d} {g['onay']:5d} "
                 f"{(f'{isabet:.0%}' if isabet is not None else '-'):>7s}")
    top_ornek = sum(g["ornek"] for g in say.values())
    top_onay = sum(g["onay"] for g in say.values())
    if top_ornek:
        L.append(f"   GENEL: {top_onay}/{top_ornek} = {top_onay / top_ornek:.0%} "
                 "(örneklem; tür başına en fazla N dilim)")
    L.append("   Not: Hakemin onaylamaması kesin yanlış alarm demek değildir; iki model de "
             "yanılabilir. Elle kontrol edilen bir örneklemle desteklenmeli.")
    L.append("")

    # 2) Taşma: yapay zeka vs piksel ölçümü
    tarama = Path(a.tarama)
    if tarama.exists():
        tasan, olculen = set(), set()
        with open(tarama, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                olculen.add(r["dosya"])
                if "TASMA" in r.get("bayraklar_str", ""):
                    tasan.add(r["dosya"])
        ai_goruntu = defaultdict(bool)   # görüntü -> ana model taşma dedi mi
        for (dosya, _), r in ana.items():
            ai_goruntu[dosya] |= "horizontal_overflow" in turler(r)
        ortak = [d for d in ai_goruntu if d in olculen]
        tp = sum(1 for d in ortak if ai_goruntu[d] and d in tasan)
        fp = sum(1 for d in ortak if ai_goruntu[d] and d not in tasan)
        fn = sum(1 for d in ortak if not ai_goruntu[d] and d in tasan)
        L.append("2) YATAY TAŞMA: YAPAY ZEKA vs PİKSEL ÖLÇÜMÜ (görüntü bazında)")
        L.append(f"   Karşılaştırılan görüntü: {len(ortak)} | kodla ölçülen taşan: "
                 f"{sum(1 for d in ortak if d in tasan)}")
        L.append(f"   Doğru tespit (TP): {tp} | yanlış alarm (FP): {fp} | kaçırılan (FN): {fn}")
        if tp + fp:
            L.append(f"   İsabet (precision): {tp / (tp + fp):.0%}  -> AI 'taşıyor' dediğinde "
                     "gerçekten taşma oranı")
        if tp + fn:
            L.append(f"   Yakalama (recall)  : {tp / (tp + fn):.0%}  -> gerçek taşmaların "
                     "kaçını AI buldu")
        L.append("   Not: Piksel ölçümü ilk çekimin görüntülerinden; yeniden çekimde sayfa "
                 "düzeni aynı kaldığı için referans olarak kullanılabilir.")
        L.append("")
    else:
        L.append(f"2) Taşma karşılaştırması atlandı: {tarama} yok\n")

    # 3) Mojibake kanıtları
    L.append("3) MOJİBAKE BULGULARININ KANITLARI (elle kontrol; tester metinde 0 mojibake ölçtü)")
    n = 0
    for model_ad, kume in ((a.ana, ana), (a.hakem, hakem)):
        for (dosya, dilim), r in sorted(kume.items()):
            for d in r["cevap"].get("defects", []):
                if d.get("type") == "mojibake" and n < 40:
                    n += 1
                    L.append(f"   [{model_ad.split(':')[-1]}] {dosya[:60]} #{dilim}")
                    L.append(f"       kanıt: {d.get('evidence_text', '')[:100]!r}")
    if n == 0:
        L.append("   (yok)")

    metin = "\n".join(L)
    (cikti / "isabet.txt").write_text(metin, encoding="utf-8")
    with open(cikti / "isabet.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cihaz", "tur", "ana_bulgu", "ornek", "onay", "isabet"],
                           delimiter=";")
        w.writeheader()
        w.writerows(satirlar)
    print(metin)
    print(f"\n💾 {cikti / 'isabet.txt'} ve isabet.csv")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
