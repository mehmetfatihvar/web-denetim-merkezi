#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 BUTON/LINK TIKLAMA DOĞRULAMA  (verify_clicks)
================================================================================
 Soru: Sayfadaki buton/link GERÇEKTEN bu (kırık) adrese mi götürüyor, yoksa
       React araya girip başka (çalışan) bir yere mi yönlendiriyor?

 Yöntem (her kırık URL için):
   1) O kırık URL'ye LİNK VEREN gerçek bir sayfa (referrer, status=200) bulunur.
   2) Referrer sayfası gerçek tarayıcıda açılır, React render beklenir.
   3) Hedefe giden <a> öğesi DOM'da bulunur ve GERÇEKTEN TIKLANIR
      (JS router varsa o çalışır).
   4) Tıklamadan sonra: nereye gitti (final URL), içerik geldi mi bakılır.

 Sonuç:
   - "KIRIGA GÖTÜRÜYOR"   : tıklayınca kırık hedefe gidiyor, içerik yok
                           (yani buton gerçekten kırık sayfaya götürüyor)
   - "ÇALIŞAN YERE GİDİYOR": tıklayınca içerik gelen bir yere gidiyor
                           (href yanıltıcı; React doğru yere yönlendiriyor)
   - "LİNK/BUTON YOK"     : referrer'da bu hedefe giden tıklanır öğe yok
   - "REFERRER AÇILMADI"  : linkleyen sayfa da yüklenemedi

--------------------------------------------------------------------------------
 KURULUM:  pip install playwright ; playwright install chromium
 ÇALIŞTIRMA (tools/ klasöründe):
     python verify_clicks.py                     # site haritasından, ilk 40
     python verify_clicks.py --limit 15          # 15 örnek
     python verify_clicks.py --only programs     # sadece /programs içerenler
 ÇIKTI:  clicks_verification.csv
================================================================================
"""
import argparse, asyncio, csv, json, os, sys, collections
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[HATA] Playwright kurulu değil: pip install playwright && playwright install chromium")
    sys.exit(1)

FORBIDDEN = ("403 forbidden", "access denied", "erişim engellendi", "forbidden",
             "404 not found", "sayfa bulunamadı", "not found")


def load_map(path):
    for c in (path, "../data/final_complete_site_map.json", "data/final_complete_site_map.json",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "final_complete_site_map.json")):
        if c and os.path.exists(c):
            return json.load(open(c, encoding="utf-8"))
    print("[HATA] final_complete_site_map.json bulunamadı (--map ile ver).")
    sys.exit(1)


def load_broken_csv(path, statuses=(401, 403, 404)):
    """Kırık link denetiminin çıktısından (broken_links.csv: url, status, kaynak_sayfa, ...)
    site içi kırık hedefler ve onlara link veren sayfalar. Her siteye uyar; site haritasında
    sayfa durumları ve linkler gerekmez."""
    broken, ref = {}, collections.defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            u, st, kaynak = r.get("url", ""), (r.get("status") or "").strip(), r.get("kaynak_sayfa", "")
            if not (st.isdigit() and int(st) in statuses) or not kaynak:
                continue
            if urlparse(u).hostname != urlparse(kaynak).hostname:     # yalnız site içi linkler
                continue
            broken[u] = int(st)
            if kaynak not in ref[u]:
                ref[u].append(kaynak)
    return broken, ref


def load_from_map(path):
    """Eski biçim: sayfa durumları ve linkleri olan site haritası ({"pages": {url: {status, links}}})."""
    data = load_map(path)
    if "pages" not in data:
        print("[HATA] Bu site haritasında sayfa durumları/linkleri yok. Önce 'Kırık link denetimi' "
              "adımını çalıştırıp --kirik-linkler ile broken_links.csv verin.")
        sys.exit(1)
    pages = data["pages"]
    broken = {u: i.get("status") for u, i in pages.items() if i.get("status") in (401, 403, 404)}
    # tersine indeks: kırık URL -> onu linkleyen 200'lük sayfalar
    ref = collections.defaultdict(list)
    for u, info in pages.items():
        if info.get("status") == 200:
            for l in info.get("links", []):
                if l in broken:
                    ref[l].append(u)
    return broken, ref


async def check_click(context, target, referrer, timeout):
    rec = {"kirik_url": target, "referrer": referrer, "referrer_status": None,
           "buton_var": False, "gidilen_url": "", "verdict": "BELİRSİZ"}
    page = await context.new_page()
    try:
        try:
            resp = await page.goto(referrer, wait_until="domcontentloaded", timeout=timeout * 1000)
            rec["referrer_status"] = resp.status if resp else None
        except Exception:
            rec["referrer_status"] = "error"
        if rec["referrer_status"] != 200:
            rec["verdict"] = "REFERRER AÇILMADI"
            return rec
        await page.wait_for_timeout(2000)

        tpath = urlparse(target).path.rstrip("/")
        found = await page.evaluate("""(tp) => {
            const a=[...document.querySelectorAll('a[href]')].find(x=>{
                try{ return new URL(x.href).pathname.replace(/\\/$/,'')===tp; }catch(e){ return false; }
            });
            if(a){ a.setAttribute('data-vc','1'); a.scrollIntoView(); return true; }
            return false;
        }""", tpath)
        rec["buton_var"] = bool(found)
        if not found:
            rec["verdict"] = "LİNK/BUTON YOK"
            return rec

        # gerçek tıklama (React router varsa çalışır)
        try:
            await page.click("a[data-vc='1']", timeout=timeout * 1000)
        except Exception:
            # bazı linkler yeni sekmede açılır; href'e göre doğrudan git
            await page.goto(target, wait_until="domcontentloaded", timeout=timeout * 1000)
        await page.wait_for_timeout(2200)

        rec["gidilen_url"] = page.url
        info = await page.evaluate("""() => {
            const len = document.body ? document.body.innerText.trim().length : 0;
            const low = (document.body ? document.body.innerText : '').toLowerCase();
            const main = !!document.querySelector('main, article, .content, #content, table, .card, nav a');
            return { len, low: low.slice(0,3000), main };
        }""")
        forbidden = any(m in info["low"] for m in FORBIDDEN)
        has_content = info["len"] > 300 and info["main"] and not forbidden
        rec["verdict"] = "ÇALIŞAN YERE GİDİYOR" if has_content else "KIRIGA GÖTÜRÜYOR"
        return rec
    finally:
        await page.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kirik-linkler", default=None,
                    help="Kırık link denetiminin broken_links.csv'si (önerilen; her sitede çalışır)")
    ap.add_argument("--map", default="../data/final_complete_site_map.json",
                    help="Eski biçim site haritası (sayfa durumları ve linkleriyle)")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--only", default=None, help="Sadece bu metni içeren kırık URL'ler (ör: programs)")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--out", default="clicks_verification.csv")
    opts = ap.parse_args()

    if opts.kirik_linkler:
        if not os.path.exists(opts.kirik_linkler):
            print(f"[HATA] {opts.kirik_linkler} yok. Önce 'Kırık link denetimi' adımını çalıştırın; "
                  "bu adım kırık adresleri ve onlara link veren sayfaları bulur.")
            sys.exit(1)
        broken, ref = load_broken_csv(opts.kirik_linkler)
        print(f"[*] Kaynak: {opts.kirik_linkler} ({len(broken)} site içi kırık hedef)")
    else:
        # Program eski sürümdeyse --map (adres listesi) gelir; kırık link denetimi çıktısı
        # çıktı klasörünün yanında varsa (ciktilar/<profil>/linkdenetim/) o kullanılır.
        yan = os.path.join(os.path.dirname(os.path.abspath(opts.out)), "linkdenetim", "broken_links.csv")
        try:
            harita_ayrintili = "pages" in load_map(opts.map)
        except Exception:
            harita_ayrintili = False
        if not harita_ayrintili and os.path.exists(yan):
            broken, ref = load_broken_csv(yan)
            print(f"[*] Kaynak: {yan} ({len(broken)} site içi kırık hedef)")
        else:
            broken, ref = load_from_map(opts.map)

    targets = [u for u in broken if ref[u]]
    if opts.only:
        targets = [u for u in targets if opts.only in u]
    targets = targets[:opts.limit]
    print(f"[*] {len(targets)} kırık URL, 200'lük referrer sayfasından tıklanarak test edilecek")

    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True, locale="tr-TR")
        sem = asyncio.Semaphore(opts.concurrency)

        biten = [0]   # eşzamanlı bittiği için listedeki sıra (i) değil, bitirilen sayı basılır

        async def guarded(t, i):
            async with sem:
                r = await check_click(context, t, ref[t][0], opts.timeout)
                biten[0] += 1
                print(f"  [{biten[0]}/{len(targets)}] {r['verdict']:22} {t[-70:]}")
                return r
        tasks = [guarded(t, i + 1) for i, t in enumerate(targets)]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)
        await browser.close()

    with open(opts.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["kirik_url", "referrer", "referrer_status", "buton_var", "gidilen_url", "verdict"])
        for r in results:
            w.writerow([r["kirik_url"], r["referrer"], r["referrer_status"], r["buton_var"], r["gidilen_url"], r["verdict"]])
    dist = collections.Counter(r["verdict"] for r in results)
    print("\n" + "=" * 60 + "\nBUTON TIKLAMA ÖZETİ\n" + "=" * 60)
    for k, v in dist.most_common():
        print(f"  {v:4}  {k}")
    print(f"\n[✓] Çıktı: {opts.out}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Durduruldu.")
