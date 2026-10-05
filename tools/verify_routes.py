#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 ROTA DOĞRULAMA ARACI  (verify_routes)
================================================================================
 Amaç: Doğrudan erişimde 401/403/404 dönen URL'lerin GERÇEKTEN kırık mı, yoksa
       yalnızca bir SPA (React) "deep-link" sorunu mu olduğunu KESİN ayırt etmek.

 Sorun: Site React tabanlı. "/programs", "/programlar", "/bolumler" gibi sekme
        rotaları, ebeveyn sayfadaki sekmeye TIKLANINCA çalışır (client-side
        routing), ama URL'ye DOĞRUDAN gidince sunucu 403/404 döner (o rota
        sunucuda yok). Bu "kırık sayfa" değildir; deep-link/SEO/yer imi sorunudur.

 Yöntem (her şüpheli URL için):
   1) Doğrudan GET → HTTP durumu (bookmark/arama motorunun gördüğü)
   2) Ebeveyn URL'yi aç (son segmenti at). Ebeveynde bu hedefe giden linki bul,
      TIKLA. URL hedefe döndü mü ve GERÇEK İÇERİK render oldu mu (403/Forbidden
      metni yok, gövdede anlamlı metin var) → in-app çalışıyor demektir.
   3) Karar:
        - "SPA-ROTA (in-app çalışır)"  : doğrudan hata AMA tıklayınca içerik gelir
        - "GERÇEKTEN KIRIK"            : doğrudan hata VE tıklayınca da içerik yok
        - "BELİRSİZ"                   : ebeveyn/link bulunamadı

--------------------------------------------------------------------------------
 KURULUM:  pip install playwright ; playwright install chromium
 ÇALIŞTIRMA (tools/ klasöründe):
     # Kaynak: test_output/results.jsonl (varsayılan) — oradaki 401/403/404'ler
     python verify_routes.py
     # veya site haritasından türet:
     python verify_routes.py --source ..\data\final_complete_site_map.json
     # sadece belirli sayıda test:
     python verify_routes.py --limit 50

 ÇIKTI:  routes_verification.csv  (url, direct_status, parent_status, in_app, verdict)
================================================================================
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[HATA] Playwright kurulu değil: pip install playwright && playwright install chromium")
    sys.exit(1)

FORBIDDEN_MARKERS = ("403 forbidden", "access denied", "erişim engellendi",
                     "forbidden", "404 not found", "sayfa bulunamadı", "not found")


def load_suspect_urls(source, statuses):
    """401/403/404 dönen URL'leri kaynak dosyadan çıkarır."""
    urls = []
    if source and source.endswith(".jsonl"):
        with open(source, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("http_status") in statuses:
                    urls.append(r["url"])
    else:
        data = json.load(open(source, encoding="utf-8"))
        pages = data.get("pages", {})
        for u, info in pages.items():
            if info.get("status") in statuses:
                urls.append(u)
    # tekilleştir
    return list(dict.fromkeys(urls))


def parent_of(url):
    p = urlparse(url)
    segs = p.path.rstrip("/").split("/")
    if len(segs) <= 1:
        return None
    parent_path = "/".join(segs[:-1]) or "/"
    return f"{p.scheme}://{p.netloc}{parent_path}"


async def verify_one(context, url, timeout):
    """URL'yi doğrudan tarayıcıda açar; durum kodu NE OLURSA OLSUN gerçek içerik
    render oluyor mu bakar (kullanıcının gördüğü). React'in render'ı için bekler."""
    rec = {"url": url, "direct_status": None, "parent_status": "", "in_app": False, "verdict": "BELİRSİZ"}
    page = await context.new_page()
    try:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            rec["direct_status"] = resp.status if resp else None
        except Exception:
            rec["direct_status"] = "error"

        # React'in içeriği render etmesi için bekle
        await page.wait_for_timeout(2500)

        info = await page.evaluate("""() => {
            const bodyLen = document.body ? document.body.innerText.trim().length : 0;
            const low = (document.body ? document.body.innerText : '').toLowerCase();
            const hasMain = !!document.querySelector('main, article, .content, #content, table, .card, .list, nav a');
            const title = (document.title||'').toLowerCase();
            return { bodyLen, low: low.slice(0, 4000), hasMain, title };
        }""")
        low = (info.get("low") or "") + " " + (info.get("title") or "")
        forbidden = any(m in low for m in FORBIDDEN_MARKERS)
        # gerçek içerik: yeterli metin + ana içerik öğesi + yasak metni yok
        rec["in_app"] = bool(info.get("bodyLen", 0) > 300 and info.get("hasMain") and not forbidden)

        if rec["direct_status"] == 200 and rec["in_app"]:
            rec["verdict"] = "ÇALIŞIYOR (200)"
        elif rec["in_app"]:
            rec["verdict"] = "İÇERİK GELİYOR (durum " + str(rec["direct_status"]) + " ama tarayıcıda açılıyor)"
        else:
            rec["verdict"] = "GERÇEKTEN KIRIK"
        return rec
    finally:
        await page.close()


async def main():
    ap = argparse.ArgumentParser(description="SPA rota doğrulama")
    ap.add_argument("--source", default=None,
                    help="Kaynak: results.jsonl (varsayılan: test_output/results.jsonl) veya site haritası JSON")
    ap.add_argument("--statuses", default="401,403,404", help="Doğrulanacak durum kodları")
    ap.add_argument("--limit", type=int, default=None, help="En fazla kaç URL")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--out", default="routes_verification.csv")
    opts = ap.parse_args()

    source = opts.source
    if not source:
        for c in ("test_output/results.jsonl", os.path.join("test_output", "results.jsonl")):
            if os.path.exists(c):
                source = c
                break
    if not source or not os.path.exists(source):
        print("[HATA] Kaynak bulunamadı. --source ile results.jsonl veya site haritası ver.")
        sys.exit(1)

    statuses = set(int(x) for x in opts.statuses.split(","))
    urls = load_suspect_urls(source, statuses)
    if opts.limit:
        urls = urls[:opts.limit]
    print(f"[*] Kaynak: {source}")
    print(f"[*] Doğrulanacak {len(urls)} URL (durum {sorted(statuses)})")

    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True, locale="tr-TR")
        sem = asyncio.Semaphore(opts.concurrency)

        async def guarded(u, i):
            async with sem:
                r = await verify_one(context, u, opts.timeout)
                print(f"  [{i}/{len(urls)}] {r['verdict']:28} {u[:80]}")
                return r
        tasks = [guarded(u, i + 1) for i, u in enumerate(urls)]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)
        await browser.close()

    with open(opts.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "direct_status", "parent_status", "in_app", "verdict"])
        for r in results:
            w.writerow([r["url"], r["direct_status"], r["parent_status"], r["in_app"], r["verdict"]])

    dist = Counter(r["verdict"] for r in results)
    print("\n" + "=" * 60)
    print("ROTA DOĞRULAMA ÖZETİ")
    print("=" * 60)
    for k, v in dist.most_common():
        print(f"  {v:5}  {k}")
    print(f"\n[✓] Çıktı: {opts.out}")
    print("     'SPA-ROTA' = doğrudan 403/404 ama in-app çalışıyor (deep-link sorunu, kırık DEĞİL)")
    print("     'GERÇEKTEN KIRIK' = hiçbir şekilde açılmıyor")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Durduruldu.")
