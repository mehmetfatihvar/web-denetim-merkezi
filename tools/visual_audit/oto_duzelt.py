"""
Herhangi bir sitede mobil yatay taşmaları bulup düzelten CSS'i otomatik üretir.

Elle yaptığımız döngünün otomatik hali:
  1) Sayfalar CSS'siz ölçülür: sayfa yana kayıyor mu, kaydıran öğe hangisi
     (tester.py'deki gizle-ölç bulucusu).
  2) Kaydıran öğe türüne göre sınıflandırılır (uzun metin, tablo, gömülü içerik,
     sabit genişlikli kutu) ve ona uygun, sitenin kendi sınıflarıyla yazılmış
     bir CSS kuralı üretilir.
  3) Kurallar sayfalara eklenip yeniden ölçülür; hâlâ kayanlar için yeni kural
     üretilir. Etkisiz kalan kural bir sonraki turda !important ile güçlendirilir.
  4) Son turda TÜM sayfalar ölçülür: CSS'siz düzgün olup CSS'li kayan sayfa
     ("yeni bozulan") varsa raporlanır.

Site değişmez; CSS yalnızca tarayıcının kendi sekmesine eklenir.

Kullanım (repo kökünden, denetim/ klasöründe):
    python oto_duzelt.py --site https://ornek.edu.tr
    python oto_duzelt.py --site https://ornek.edu.tr --limit 300 --cihaz ikisi
    python oto_duzelt.py --urls ..\\data\\final_complete_site_map.json --limit 400

Çıktı (oto_cikti/):
    oneri.css      geliştiriciye verilecek CSS (her kuralın üstünde kaç sayfayı düzelttiği)
    turlar.csv     tur başına kayan / düzelen / yeni bozulan sayfa sayısı
    sayfalar.csv   sayfa başına önce/sonra taşma ve kaydıran öğe
    ozet.txt       kısa özet
    goruntu/       önce/sonra mobil görüntüler + karsilastir.html (gözle kontrol için)
"""
import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter, defaultdict, OrderedDict
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

# Çekim aracı: gorsel-denetim reposunda ../cekim/tester.py, Web Denetim Merkezi'nde
# ../tester_v3_evidence.py (aynı araç). Hangisi varsa o kullanılır.
_ARACLAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ARACLAR / "cekim"))
sys.path.insert(0, str(_ARACLAR))
try:
    from tester import SAYFA_GENISLIK_JS, DESKTOP_VIEWPORT, MOBILE_VIEWPORT, safe_name  # noqa: E402
except ImportError:
    from tester_v3_evidence import (SAYFA_GENISLIK_JS, DESKTOP_VIEWPORT,  # noqa: E402
                                    MOBILE_VIEWPORT, safe_name)

CIHAZ = {"mobile": MOBILE_VIEWPORT, "desktop": DESKTOP_VIEWPORT}
BELGE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|jpe?g|png|gif|mp4|mp3)$", re.I)

# SAYFA_GENISLIK_JS'nin işaretlediği öğeyi sınıflandırır ve genelleştirilmiş bir seçici
# üretir. Seçici sitenin kendi sınıflarından kurulur; sınıfsız öğe (p, a, span) en
# yakın sınıflı atasıyla kapsamlanır (".prose p"), flex/grid çocuğu "ata > öğe" olur.
SINIFLA_JS = r"""() => {
  const el = document.querySelector('[data-genisleten]');
  if (!el) return null;
  // derleyici/üçüncü taraf üretimi sınıflar (n6owBd, css-1x2y3z...) sürüm değişince değişir;
  // seçiciye girmez. Tailwind/Bootstrap'te rakamlı sınıflar tireli olur (mt-4, col-md-6).
  const uretilmis = (c) => /\d{4,}|^css-|^sc-|^jsx-|__/.test(c) || (!c.includes('-') && /\d/.test(c) && c.length >= 5);
  const sinifli = (e) => {
    const tag = e.tagName.toLowerCase();
    const cls = (typeof e.className === 'string' ? e.className.trim().split(/\s+/) : [])
                  .filter(c => c && !uretilmis(c)).slice(0, 2);
    return cls.length ? tag + cls.map(c => '.' + CSS.escape(c)).join('') : null;
  };
  const kapsamli = (e) => {
    const kendi = sinifli(e);
    if (kendi) return kendi;
    const tag = e.tagName.toLowerCase();
    for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
      const s = sinifli(a);
      if (s) return s + ' ' + tag;
    }
    return tag;
  };
  const st = getComputedStyle(el);
  const tag = el.tagName.toLowerCase();
  const ata = el.parentElement;
  const ataDisp = ata ? getComputedStyle(ata).display : '';
  const flexCocuk = /flex|grid/.test(ataDisp);
  const kendiMetni = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  let tur, secici;
  if (['iframe', 'video', 'embed', 'object', 'img', 'canvas', 'svg'].includes(tag)) {
    tur = 'gomulu'; secici = tag;
  } else if (el.closest('table')) {
    // iç içe tablolarda en dıştaki tablo kaydırılmalı; içtekini kaydırmak dıştakini daraltmaz
    let t = el.closest('table');
    while (t.parentElement && t.parentElement.closest('table')) t = t.parentElement.closest('table');
    tur = 'tablo'; secici = kapsamli(t);
  } else if (tag === 'pre' || /^pre/.test(st.whiteSpace)) {
    tur = 'onbicimli'; secici = kapsamli(el);
  } else if ((kendiMetni || (el.innerText || '').trim()) &&
             (/^inline/.test(st.display) || flexCocuk || el.scrollWidth > el.clientWidth + 1)) {
    // metin kendi kutusundan taşıyor (ya da satır içi / flex öğesi metnine göre genişliyor)
    tur = 'metin';
    const kendi = sinifli(el);
    secici = flexCocuk && ata ? (sinifli(ata) || kapsamli(ata)) + ' > ' + (kendi || tag) : kapsamli(el);
  } else {
    tur = 'kutu'; secici = kapsamli(el);
  }
  return {tur, secici, nowrap: /nowrap|pre/.test(st.whiteSpace), flexCocuk,
          metin: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60)};
}"""


def kural_govdesi(tur, nowrap, flex_cocuk, onemli):
    imp = " !important" if onemli else ""
    if tur == "gomulu":
        satirlar = [f"max-width: 100%{imp}", f"box-sizing: border-box{imp}"]
    elif tur == "tablo":
        satirlar = [f"display: block{imp}", f"max-width: 100%{imp}", f"overflow-x: auto{imp}"]
    elif tur == "onbicimli":
        satirlar = [f"max-width: 100%{imp}", f"overflow-x: auto{imp}"]
    elif tur == "metin":
        satirlar = [f"overflow-wrap: anywhere{imp}"]
        if nowrap:
            satirlar.append(f"white-space: normal{imp}")
        if flex_cocuk:
            satirlar.append(f"min-width: 0{imp}")
    else:  # kutu
        satirlar = [f"max-width: 100%{imp}", f"box-sizing: border-box{imp}"]
    return satirlar


class Kurallar:
    """Seçici başına tek kural; özellikler birleşir, etkisiz kalan kural !important olur."""

    def __init__(self):
        self.k = OrderedDict()   # secici -> dict

    def ekle(self, bilgi, sayfalar, tur_no):
        sec = bilgi["secici"]
        if sec in ("html", "body"):
            return False
        mevcut = self.k.get(sec)
        if mevcut is None:
            self.k[sec] = {"tur": bilgi["tur"], "nowrap": bilgi["nowrap"], "flex": bilgi["flexCocuk"],
                           "onemli": False, "sayfa": set(sayfalar), "ornek": bilgi.get("metin", ""),
                           "eklendigi_tur": tur_no}
            return True
        degisti = False
        if bilgi["tur"] != mevcut["tur"]:   # yeni ölçüm öğeyi başka türde gördü
            mevcut.update(tur=bilgi["tur"], onemli=False)
            degisti = True
        for alan, deger in (("nowrap", bilgi["nowrap"]), ("flex", bilgi["flexCocuk"])):
            if deger and not mevcut[alan]:
                mevcut[alan] = True
                degisti = True
        if not degisti and not mevcut["onemli"]:
            mevcut["onemli"] = True   # kural vardı ama öğe hâlâ taşıyor: özgüllükte yeniliyor
            degisti = True
        mevcut["sayfa"].update(sayfalar)
        return degisti

    def etkisizleri_cikar(self, duzelen_sayfalar):
        """Hedeflediği sayfalardan hiçbirini düzeltmeyen kuralı CSS'ten çıkarır."""
        cikan = [s for s, k in self.k.items() if not (k["sayfa"] & duzelen_sayfalar)]
        for s in cikan:
            del self.k[s]
        return cikan

    def css(self, aciklamali=False):
        parcalar = []
        if aciklamali:
            parcalar.append("/* oto_duzelt.py ile üretildi. Her kural ölçülerek eklendi;\n"
                            "   'sayfa' = kuralın hedeflediği öğenin sayfayı kaydırdığı sayfa sayısı. */\n")
        for sec, k in self.k.items():
            govde = kural_govdesi(k["tur"], k["nowrap"], k["flex"], k["onemli"])
            if aciklamali:
                ornek = f", örnek metin: {k['ornek'][:40]!r}" if k["ornek"] else ""
                parcalar.append(f"/* {k['tur']}: {len(k['sayfa'])} sayfa, {k['eklendigi_tur']}. tur{ornek} */")
            parcalar.append(sec + " {\n" + "".join(f"  {s};\n" for s in govde) + "}\n")
        return "\n".join(parcalar)


# --------------------------------------------------------------------------- URL'ler
def harita_oku(yol):
    data = json.loads(Path(yol).read_text(encoding="utf-8"))
    return data["url_list"] if isinstance(data, dict) else data


async def sitemap_oku(istek, site, sinir):
    urls, kuyruk, gorulen = [], [urljoin(site, "/sitemap.xml")], set()
    while kuyruk and len(urls) < sinir * 5 and len(gorulen) < 20:
        adres = kuyruk.pop(0)
        if adres in gorulen:
            continue
        gorulen.add(adres)
        try:
            yanit = await istek.get(adres, timeout=15000)
            if not yanit.ok:
                continue
            kok = ElementTree.fromstring(await yanit.body())
        except Exception:
            continue
        for loc in kok.iter():
            if loc.tag.endswith("loc") and loc.text:
                (kuyruk if loc.text.strip().endswith(".xml") else urls).append(loc.text.strip())
    return urls


async def tara(baglam, site, sinir):
    """sitemap.xml yoksa aynı alan adındaki linkleri izleyerek sayfa toplar (JS ile çizilen linkler dahil)."""
    host = urlparse(site).netloc
    bulunan, kuyruk = OrderedDict(), [site]
    sayfa = await baglam.new_page()
    while kuyruk and len(bulunan) < sinir * 3:
        url = kuyruk.pop(0).split("#")[0]
        if url in bulunan:
            continue
        bulunan[url] = True
        try:
            await sayfa.goto(url, wait_until="load", timeout=30000)
            linkler = await sayfa.eval_on_selector_all("a[href]", "as => as.map(a => a.href)")
        except Exception:
            continue
        for l in linkler:
            l = l.split("#")[0]
            if urlparse(l).netloc == host and l.startswith("http") and not BELGE.search(l) and l not in bulunan:
                kuyruk.append(l)
    await sayfa.close()
    return list(bulunan)


def orneklem(urls, sinir):
    """Şablon çeşitliliği için ilk iki yol parçasına göre gruplayıp sırayla seçer."""
    gruplar = defaultdict(list)
    for u in OrderedDict.fromkeys(urls):
        parca = [p for p in urlparse(u).path.split("/") if p][:2]
        gruplar["/".join(parca)].append(u)
    secilen, listeler = [], list(gruplar.values())
    while len(secilen) < sinir and any(listeler):
        for l in listeler:
            if l and len(secilen) < sinir:
                secilen.append(l.pop(0))
    return secilen


# --------------------------------------------------------------------------- ölçüm
async def olc(baglam, url, cihazlar, css, sem, zaman_asimi):
    async with sem:
        sayfa = await baglam.new_page()
        sonuc = {}
        try:
            yanit = await sayfa.goto(url, wait_until="load", timeout=zaman_asimi * 1000)
            if yanit and yanit.status >= 400:
                return url, {"hata": f"HTTP {yanit.status}"}
            if css:
                await sayfa.add_style_tag(content=css)
            for c in cihazlar:
                await sayfa.set_viewport_size(CIHAZ[c])
                await sayfa.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await sayfa.wait_for_timeout(400)
                await sayfa.evaluate("() => window.scrollTo(0, 0)")
                g = await sayfa.evaluate(SAYFA_GENISLIK_JS)
                bilgi = await sayfa.evaluate(SINIFLA_JS) if g.get("kayiyor") else None
                sonuc[c] = {"kayiyor": bool(g.get("kayiyor")),
                            "px": max(0, (g.get("scroll") or 0) - (g.get("client") or 0)),
                            "bilgi": bilgi}
        except Exception as e:
            sonuc["hata"] = str(e)[:160]
        finally:
            await sayfa.close()
        return url, sonuc


async def tur_olc(baglam, urls, cihazlar, css, a):
    sem = asyncio.Semaphore(a.eszamanli)
    gorevler = [olc(baglam, u, cihazlar, css, sem, a.zaman_asimi) for u in urls]
    sonuc, n = {}, 0
    for f in asyncio.as_completed(gorevler):
        url, s = await f
        sonuc[url] = s
        n += 1
        if n % 25 == 0 or n == len(urls):
            print(f"    {n}/{len(urls)}", flush=True)
    return sonuc


async def goruntu_al(baglam, url, css, yol):
    sayfa = await baglam.new_page()
    try:
        await sayfa.set_viewport_size(MOBILE_VIEWPORT)
        await sayfa.goto(url, wait_until="load", timeout=30000)
        if css:
            await sayfa.add_style_tag(content=css)
        await sayfa.wait_for_timeout(500)
        boy = await sayfa.evaluate("() => Math.min(document.documentElement.scrollHeight, 2400)")
        gen = await sayfa.evaluate("() => document.documentElement.scrollWidth")
        await sayfa.screenshot(path=str(yol), full_page=True,
                               clip={"x": 0, "y": 0, "width": gen, "height": boy})
    except Exception:
        pass
    finally:
        await sayfa.close()


# --------------------------------------------------------------------------- ana akış
async def calistir(a):
    from playwright.async_api import async_playwright

    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    cihazlar = ["mobile", "desktop"] if a.cihaz == "ikisi" else [a.cihaz]

    async with async_playwright() as pw:
        tarayici = await pw.chromium.launch(**({"executable_path": a.chromium} if a.chromium else {}))
        baglam = await tarayici.new_context(ignore_https_errors=True, viewport=MOBILE_VIEWPORT)

        if a.urls:
            urls = harita_oku(a.urls)
            print(f"[*] {len(urls)} URL haritadan okundu")
        else:
            urls = await sitemap_oku(baglam.request, a.site, a.limit)
            print(f"[*] sitemap.xml: {len(urls)} URL")
            if not urls:
                print("[*] sitemap yok, linkler izlenerek taranıyor...")
                urls = await tara(baglam, a.site, a.limit)
                print(f"[*] tarama: {len(urls)} URL")
        urls = orneklem(urls, a.limit)
        if not urls:
            sys.exit("[HATA] ölçülecek sayfa bulunamadı.")
        print(f"[*] {len(urls)} sayfa ölçülecek ({', '.join(cihazlar)})\n")

        print("[0] CSS'siz ölçüm")
        once = await tur_olc(baglam, urls, cihazlar, "", a)
        kayan = lambda olcum, u, c: bool((olcum.get(u) or {}).get(c, {}).get("kayiyor"))  # noqa: E731
        hedef = [u for u in urls if any(kayan(once, u, c) for c in cihazlar)]
        kurallar, turlar, son = Kurallar(), [], once

        for tur_no in range(1, a.tur + 1):
            # kalan kaydıran öğelerden kural üret
            gruplar = defaultdict(list)
            for u in hedef:
                for c in cihazlar:
                    b = (son.get(u) or {}).get(c, {}).get("bilgi")
                    if kayan(son, u, c) and b:
                        gruplar[(b["secici"], b["tur"])].append((u, b))
            yeni = 0
            for (_, _), liste in sorted(gruplar.items(), key=lambda x: -len(x[1])):
                bilgi = dict(liste[0][1])
                bilgi["nowrap"] = any(b["nowrap"] for _, b in liste)
                bilgi["flexCocuk"] = any(b["flexCocuk"] for _, b in liste)
                yeni += kurallar.ekle(bilgi, [u for u, _ in liste], tur_no)
            if not yeni:
                print(f"[{tur_no}] yeni kural yok, döngü bitti")
                break
            print(f"[{tur_no}] {len(kurallar.k)} kural ile ölçüm ({yeni} yeni/güçlendirilmiş)")
            son_tur = tur_no == a.tur
            son = await tur_olc(baglam, urls if son_tur else hedef, cihazlar, kurallar.css(), a)
            turlar.append((tur_no, son_tur, dict(son)))
            if all(not kayan(son, u, c) for u in hedef for c in cihazlar):
                print("    hedef sayfaların hepsi düzeldi")
                break

        # Son ölçüm tüm sayfaları kapsamıyorsa (döngü erken bittiyse) regresyon için bir kez daha
        if not turlar or not turlar[-1][1]:
            print("[son] tüm sayfalar CSS'li ölçülüyor (yeni bozulan kontrolü)")
            son = await tur_olc(baglam, urls, cihazlar, kurallar.css(), a)
            turlar.append(("son", True, dict(son)))

        duzelen = {u for u in urls for c in cihazlar if kayan(once, u, c) and not kayan(son, u, c)}
        etkisiz = kurallar.etkisizleri_cikar(duzelen)

        # ---- raporlar
        satirlar_tur, ozet = [], []
        for tur_no, _, olcum in [(0, True, once)] + turlar:
            for c in cihazlar:
                k = sum(kayan(olcum, u, c) for u in urls if u in olcum)
                duz = sum(kayan(once, u, c) and u in olcum and not kayan(olcum, u, c) for u in urls)
                bozulan = sum(u in olcum and not kayan(once, u, c) and kayan(olcum, u, c) for u in urls)
                satirlar_tur.append({"tur": tur_no, "cihaz": c, "olculen": len(olcum), "kayan": k,
                                     "duzelen": duz if tur_no else "", "yeni_bozulan": bozulan if tur_no else ""})
        yaz_csv(cikti / "turlar.csv", satirlar_tur)

        satirlar_sayfa = []
        for u in urls:
            for c in cihazlar:
                o, s = (once.get(u) or {}).get(c, {}), (son.get(u) or {}).get(c, {})
                if not o.get("kayiyor") and not s.get("kayiyor"):
                    continue
                durum = ("DUZELDI" if o.get("kayiyor") and not s.get("kayiyor") else
                         "KALDI" if o.get("kayiyor") else "YENI_BOZULDU")
                satirlar_sayfa.append({"durum": durum, "cihaz": c, "url": u,
                                       "once_px": o.get("px", ""), "sonra_px": s.get("px", ""),
                                       "once_oge": (o.get("bilgi") or {}).get("secici", ""),
                                       "sonra_oge": (s.get("bilgi") or {}).get("secici", ""),
                                       "metin": ((s.get("bilgi") or o.get("bilgi")) or {}).get("metin", "")})
        yaz_csv(cikti / "sayfalar.csv", sorted(satirlar_sayfa, key=lambda r: (r["durum"], r["cihaz"])))
        (cikti / "oneri.css").write_text(kurallar.css(aciklamali=True), encoding="utf-8")

        hatali = [u for u in urls if "hata" in (once.get(u) or {})]
        ozet += ["=" * 66, "OTOMATİK TAŞMA DÜZELTME", "=" * 66,
                 f"Ölçülen sayfa: {len(urls)}  (yüklenemeyen: {len(hatali)})", ""]
        for c in cihazlar:
            k0 = sum(kayan(once, u, c) for u in urls)
            d = sum(r["durum"] == "DUZELDI" for r in satirlar_sayfa if r["cihaz"] == c)
            kal = sum(r["durum"] == "KALDI" for r in satirlar_sayfa if r["cihaz"] == c)
            yb = sum(r["durum"] == "YENI_BOZULDU" for r in satirlar_sayfa if r["cihaz"] == c)
            oran = f"{d / k0:.0%}" if k0 else "-"
            ozet.append(f"{c:8s} yana kayan {k0:4d} -> düzeldi {d:4d} ({oran}), kaldı {kal:4d}, yeni bozulan {yb:3d}")
        ozet += ["", f"Üretilen kural: {len(kurallar.k)}  -> {cikti / 'oneri.css'}"]
        if etkisiz:
            ozet.append(f"Hiçbir sayfayı düzeltmediği için çıkarılan kural: {', '.join(etkisiz)}")
        kalan = Counter(r["sonra_oge"] for r in satirlar_sayfa if r["durum"] != "DUZELDI" and r["sonra_oge"])
        if kalan:
            ozet += ["", "Otomatik düzeltilemeyen (elle bakılmalı):"]
            ozet += [f"  {n:4d} sayfa  {s}" for s, n in kalan.most_common(10)]
        ozet += ["", "Ölçüm yalnızca yana kaymayı yakalar; görünüm için goruntu/karsilastir.html'e bakın."]
        metin = "\n".join(ozet)
        print("\n" + metin)
        (cikti / "ozet.txt").write_text(metin + "\n", encoding="utf-8")

        # ---- önce/sonra görüntüler
        if a.goruntu:
            gdir = cikti / "goruntu"
            gdir.mkdir(exist_ok=True)
            secilen = [r["url"] for r in satirlar_sayfa if r["durum"] == "DUZELDI" and r["cihaz"] == "mobile"]
            secilen = list(OrderedDict.fromkeys(secilen))[:a.goruntu]
            css = kurallar.css()
            for u in secilen:
                ad = safe_name(u, 80)
                await goruntu_al(baglam, u, "", gdir / f"{ad}_once.png")
                await goruntu_al(baglam, u, css, gdir / f"{ad}_sonra.png")
            satir = "".join(
                f"<h3>{u}</h3><div class=s><figure><img src='{safe_name(u, 80)}_once.png'><figcaption>önce</figcaption>"
                f"</figure><figure><img src='{safe_name(u, 80)}_sonra.png'><figcaption>sonra</figcaption></figure></div>"
                for u in secilen)
            (gdir / "karsilastir.html").write_text(
                "<!doctype html><meta charset=utf-8><title>Önce / sonra</title><style>body{font:14px sans-serif;"
                "margin:16px}.s{display:flex;gap:16px;overflow-x:auto}figure{margin:0}img{border:1px solid #ccc;"
                "display:block}h3{font-size:13px;word-break:break-all}</style>"
                "<p>Kırmızı çizgi yok: sol görüntü CSS'siz, sağ CSS'li. Sağdakinin genişliği 375 px olmalı.</p>"
                + satir, encoding="utf-8")
            print(f"[*] {len(secilen)} sayfanın önce/sonra görüntüsü -> {gdir / 'karsilastir.html'}")

        await tarayici.close()


def yaz_csv(yol, satirlar):
    if not satirlar:
        yol.write_text("", encoding="utf-8")
        return
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0]), delimiter=";")
        w.writeheader()
        w.writerows(satirlar)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    kaynak = ap.add_mutually_exclusive_group(required=True)
    kaynak.add_argument("--site", help="Sitenin ana adresi (sitemap.xml ya da link taramasıyla sayfa bulunur)")
    kaynak.add_argument("--urls", help='Hazır URL listesi (JSON: {"url_list": [...]} ya da [...])')
    ap.add_argument("--limit", type=int, default=200, help="Ölçülecek en fazla sayfa (şablonlara yayılarak seçilir)")
    ap.add_argument("--cihaz", choices=["mobile", "desktop", "ikisi"], default="mobile")
    ap.add_argument("--tur", type=int, default=4, help="En fazla düzeltme turu")
    ap.add_argument("--eszamanli", type=int, default=4)
    ap.add_argument("--zaman-asimi", type=int, default=30, help="Sayfa başına saniye")
    ap.add_argument("--goruntu", type=int, default=12, help="Önce/sonra görüntüsü alınacak sayfa sayısı (0 = alma)")
    ap.add_argument("--cikti", default="oto_cikti")
    ap.add_argument("--chromium", default=None, help="Chromium yolu (gerekirse)")
    a = ap.parse_args()
    asyncio.run(calistir(a))


if __name__ == "__main__":
    main()
