#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 ŞABLON KÜMELEME  (cluster_templates)
================================================================================
 Amaç: 17.394 URL'yi DÜZEN (template) imzasına göre gruplar. Aynı düzenden
       üretilen sayfalar (ör. tüm bölümlerdeki 'program-hedefleri' sayfaları)
       tek kümeye düşer. Görsel kusurlar şablon seviyesinde olduğundan, her
       şablondan yalnız birkaç TEMSİLCİ test etmek yeterlidir:
         • aynı kusur 455 kez değil 1 kez raporlanır (gürültü biter),
         • false positive'i 455 kez değil 1 kez elersin,
         • bulgu aksiyona döner: "X şablonu (≈3.000 sayfa) taşıyor -> tek düzeltme".

 ÇALIŞTIRMA:
     python cluster_templates.py                       # varsayılan site haritası
     python cluster_templates.py --reps 3              # şablon başına 3 temsilci
     python cluster_templates.py --source ..\\data\\final_complete_site_map.json

 ÇIKTILAR (data/ altına):
     template_clusters.json         imza -> {count, reps, example}  (rapor bunu kullanır)
     template_representatives.json  {"url_list":[...]}  -> tester --source ile doğrudan test
================================================================================
"""
import argparse
import json
import os
import sys

# imza fonksiyonunu ana araçtan al (tek kaynak -> rapor ile tutarlı)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter  # noqa: E402
from tester_v3_evidence import template_signature, load_urls, _leaf_of  # noqa: E402


def find_source(source):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dirs = [".", "data", os.path.join("..", "data"),
            os.path.join(script_dir, "..", "data"), script_dir]
    cands = [source] + [os.path.join(d, os.path.basename(source)) for d in dirs] + \
            [os.path.join(d, "final_complete_site_map.json") for d in dirs]
    return next((c for c in cands if os.path.exists(c)), None)


def out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(script_dir, "..", "data"), os.path.join("..", "data"), "data", "."):
        if os.path.isdir(d):
            return d
    return "."


def main():
    ap = argparse.ArgumentParser(description="URL'leri şablon düzenine göre kümele")
    ap.add_argument("--source", default="final_complete_site_map.json")
    ap.add_argument("--reps", type=int, default=3, help="Şablon başına temsilci sayısı (varsayılan 3)")
    ap.add_argument("--leaf-min", type=int, default=5,
                    help="Bir yaprak segmentin SAYFA-TİPİ sayılması için gereken min tekrar (varsayılan 5); "
                         "daha az tekrar eden yapraklar varlık adı kabul edilip '*'a indirgenir")
    ap.add_argument("--cikti-klasor", default=None,
                    help="template_*.json dosyalarının yazılacağı klasör (varsayılan: repo data/)")
    opts = ap.parse_args()

    src = find_source(opts.source)
    if not src:
        print(f"[HATA] Link kaynağı bulunamadı: {opts.source}")
        sys.exit(1)
    urls = load_urls(src, None, 0)
    print(f"[*] Kaynak: {src}  ({len(urls)} URL)")

    # 1. GEÇİŞ: yaprak segment frekansı -> sık tekrar edenler "sayfa-tipi" sözlüğü
    leaf_freq = Counter(_leaf_of(u)[1] for u in urls)
    leaf_vocab = {leaf for leaf, n in leaf_freq.items()
                  if leaf and leaf != "*" and n >= opts.leaf_min}
    print(f"[*] Yaprak sözlüğü: {len(leaf_vocab)} sayfa-tipi (>= {opts.leaf_min} tekrar); "
          f"nadir yapraklar '*' (varlık) olarak toplanır")

    # 2. GEÇİŞ: sözlükle imzala
    groups = {}
    for u in urls:
        groups.setdefault(template_signature(u, leaf_vocab), []).append(u)

    clusters, reps = [], []
    for sig, us in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        us_sorted = sorted(us)
        # temsilciler: baş / orta / son -> çeşitlilik
        take = min(opts.reps, len(us_sorted))
        idx = sorted({0, len(us_sorted) // 2, len(us_sorted) - 1})[:take] if take > 1 else [0]
        r = [us_sorted[i] for i in idx][:take]
        reps.extend(r)
        clusters.append({"signature": sig, "count": len(us_sorted),
                         "reps": r, "example": us_sorted[0]})

    od = opts.cikti_klasor or out_dir()
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, "template_clusters.json"), "w", encoding="utf-8") as f:
        json.dump({"total_urls": len(urls), "template_count": len(clusters),
                   "leaf_min": opts.leaf_min, "leaf_vocab": sorted(leaf_vocab),
                   "clusters": clusters}, f, ensure_ascii=False, indent=2)
    reps = list(dict.fromkeys(reps))  # tekilleştir, sırayı koru
    with open(os.path.join(od, "template_representatives.json"), "w", encoding="utf-8") as f:
        json.dump({"url_list": reps}, f, ensure_ascii=False, indent=2)

    print(f"[✓] {len(urls)} sayfa -> {len(clusters)} şablon.  Test edilecek temsilci: {len(reps)}")
    print(f"    En büyük 12 şablon:")
    for c in clusters[:12]:
        print(f"      {c['count']:6}  {c['signature'][:60]:60}  ör: {c['example'][:50]}")
    print(f"\n[✓] Yazıldı: {od}/template_clusters.json , template_representatives.json")
    print(f"    Sıradaki: python tester_v3_evidence.py --source template_representatives.json "
          f"--out-dir gorsel --check-visual --no-screenshots --fresh")


if __name__ == "__main__":
    main()
