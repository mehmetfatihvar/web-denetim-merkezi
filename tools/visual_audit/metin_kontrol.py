#!/usr/bin/env python3
"""
Metin kodlama denetimi (kodla, yapay zekasız)

Yapay zeka incelemesi İngilizce sayfalarda Türkçe karakterlerin '?' ile
değiştirildiğini (Atat?rk, ?ZT?RK) ve HTML kodlarının ekrana basıldığını
(Master&#39;s) buldu. cekim/tester.py yalnızca 'Ã¼' tipi mojibake
aradığı için bunları kaçırmıştı. Bu script her sayfanın görünen metninde
(innerText) şu kalıpları arar:

  soru_isareti   : harfler arasında '?' (H?seyin, Atat?rk) veya büyük harf
                   kelime başında '?' (?ZT?RK) -> Türkçe karakter kaybı
  html_kodu      : görünen metinde &#39; &amp; &quot; &nbsp; gibi HTML kodları
  mojibake       : Ã Ä Å Â ile başlayan bozuk UTF-8 dizileri
  yer_tutucu     : U+FFFD (�) yerine koyma karakteri
  html_etiketi   : görünen metinde <span class=...>, </p> gibi HTML etiketleri

Adres gibi görünen kelimelerdeki eşleşmeler (index.aspx?lang=tr gibi) sayılmaz.

Kullanım:
  python metin_kontrol.py --source temsilci_urls.json
  python metin_kontrol.py --source ..\\data\\final_complete_site_map.json --limit 2000

Çıktı: metin_kontrol.csv (sayfa başına bulgu) + ekranda özet
"""

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HARF = "A-Za-zÇĞİÖŞÜçğıöşü"
DESENLER = {
    "soru_isareti": re.compile(rf"(?<=[{HARF}])\?(?=[{HARF}])|(?<![{HARF}?])\?(?=[A-ZÇĞİÖŞÜ]{{2,}})"),
    "html_kodu": re.compile(r"&(?:#\d{2,5}|#x[0-9a-fA-F]{2,4}|amp|quot|lt|gt|nbsp|apos);"),
    "mojibake": re.compile(r"[ÃÄÅÂ][\x80-\xbfŒ-Ÿˆ-›]"),
    "yer_tutucu": re.compile("�"),
    # Kapalı etiket (<span ...>, </p>) ya da uzun öznitelikli açılış başlangıcı (<span class=...)
    "html_etiketi": re.compile(
        r"</?(?:span|div|p|br|strong|em|b|i|a|ul|li|table|td|tr|font)\b[^<>]{0,300}>"
        r"|<(?:span|div|p|a|font|table|td|img)\s+(?:class|style|href|id|src|align)\s*=",
        re.IGNORECASE),
}
ADRES = re.compile(r"https?:|www\.|\.(?:aspx|php|html?|jsp|asp)\b|[=&/\\]")


def kelime(metin, m):
    """Eşleşmenin içinde bulunduğu boşluksuz kelime (adres mi diye bakmak için)."""
    bas, son = m.start(), m.end()
    while bas > 0 and not metin[bas - 1].isspace():
        bas -= 1
    while son < len(metin) and not metin[son].isspace():
        son += 1
    return metin[bas:son]


def baglam(metin, m, genislik=25):
    bas, son = max(0, m.start() - genislik), min(len(metin), m.end() + genislik)
    return metin[bas:son].replace("\n", " ").strip()


def urlleri_oku(kaynak, limit):
    veri = json.loads(Path(kaynak).read_text(encoding="utf-8"))
    if isinstance(veri, dict):
        urls = veri.get("url_list") or veri.get("urls") or list(veri.get("pages", {}).keys())
    else:
        urls = [x["url"] if isinstance(x, dict) else x for x in veri]
    urls = [u for u in dict.fromkeys(urls) if isinstance(u, str) and u.startswith("http")]
    return urls[:limit] if limit else urls


async def sayfa_tara(tarayici, url, zaman_asimi, sem):
    async with sem:
        ctx = await tarayici.new_context(ignore_https_errors=True, locale="tr-TR")
        sayfa = await ctx.new_page()
        sonuc = {"url": url, "durum": None, "hata": "", "bulgular": {}}
        try:
            yanit = await sayfa.goto(url, wait_until="load", timeout=zaman_asimi * 1000)
            sonuc["durum"] = yanit.status if yanit else None
            try:
                await sayfa.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            metin = await sayfa.evaluate("() => document.body ? document.body.innerText : ''")
            for ad, desen in DESENLER.items():
                eslesmeler = list(desen.finditer(metin))
                if ad == "soru_isareti":   # adreslerdeki ?lang=tr gibi sorgu işaretlerini ele
                    eslesmeler = [m for m in eslesmeler if not ADRES.search(kelime(metin, m))]
                if eslesmeler:
                    sonuc["bulgular"][ad] = {
                        "adet": len(eslesmeler),
                        "ornekler": list(dict.fromkeys(baglam(metin, m) for m in eslesmeler))[:3],
                    }
        except Exception as e:
            sonuc["hata"] = str(e)[:200]
        finally:
            await ctx.close()
        return sonuc


async def calistir(urls, paralel, zaman_asimi, chromium=None):
    from playwright.async_api import async_playwright
    sem = asyncio.Semaphore(paralel)
    sonuclar = []
    async with async_playwright() as p:
        tarayici = await p.chromium.launch(executable_path=chromium or None)
        gorevler = [sayfa_tara(tarayici, u, zaman_asimi, sem) for u in urls]
        for i, gorev in enumerate(asyncio.as_completed(gorevler), 1):
            sonuclar.append(await gorev)
            if i % 50 == 0 or i == len(urls):
                print(f"  [{i}/{len(urls)}]", flush=True)
        await tarayici.close()
    return sonuclar


def main():
    p = argparse.ArgumentParser(description="Görünen metinde kodlama hatası denetimi")
    p.add_argument("--source", default="temsilci_urls.json")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--paralel", type=int, default=4)
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--cikti", default="metin_kontrol.csv")
    p.add_argument("--chromium", help="İsteğe bağlı Chromium çalıştırılabilir yolu")
    a = p.parse_args()

    urls = urlleri_oku(a.source, a.limit)
    print(f"🔎 {len(urls)} sayfanın görünen metni taranıyor...")
    sonuclar = asyncio.run(calistir(urls, a.paralel, a.timeout, a.chromium))

    with open(a.cikti, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["url", "dil", "http", "desen", "adet", "ornek1", "ornek2", "ornek3", "hata"])
        for s in sorted(sonuclar, key=lambda x: x["url"]):
            dil = s["url"].split("/")[3] if s["url"].count("/") >= 3 else ""
            if not s["bulgular"]:
                w.writerow([s["url"], dil, s["durum"], "", 0, "", "", "", s["hata"]])
            for ad, b in s["bulgular"].items():
                orn = b["ornekler"] + [""] * 3
                w.writerow([s["url"], dil, s["durum"], ad, b["adet"], *orn[:3], s["hata"]])

    sayfa_say = Counter()
    dil_say = defaultdict(Counter)
    for s in sonuclar:
        dil = s["url"].split("/")[3] if s["url"].count("/") >= 3 else ""
        for ad in s["bulgular"]:
            sayfa_say[ad] += 1
            dil_say[ad][dil] += 1
    hatali = sum(1 for s in sonuclar if s["hata"])
    print(f"\n{'=' * 60}\nMETİN KODLAMA DENETİMİ ({len(sonuclar)} sayfa, {hatali} açılamadı)\n{'=' * 60}")
    for ad in DESENLER:
        dagilim = ", ".join(f"{d or '-'}: {n}" for d, n in dil_say[ad].most_common())
        print(f"  {ad:14s} {sayfa_say[ad]:5d} sayfa   ({dagilim})")
    print(f"\n💾 {a.cikti}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
