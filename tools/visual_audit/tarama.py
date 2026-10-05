#!/usr/bin/env python3
"""
Görsel Denetim - Aşama 1: Kodla Tarama + Şablon Gruplama

34 bin ekran görüntüsünün hepsini yapay zekaya sormadan önce:
  1. Ucuz ve kesin kontrolleri kodla yapar:
       - Yatay taşma (görüntü genişliği viewport'tan büyük)
       - Boş / tek renk sayfa
       - Anormal kısa / uzun sayfa
       - Masaüstü veya mobil eşi eksik sayfa
       - Farklı URL'lerde birebir aynı görünen sayfalar (soft-404, yönlendirme, boş içerik)
  2. Sayfaları URL kalıbına göre şablon gruplarına, grup içinde de görsel
     benzerliğe göre alt kümelere ayırır
  3. Her gruptan yapay zekaya sorulacak temsilci görüntüleri seçer

Kullanım:
  python tarama.py --klasor C:\\Users\\MFV\\Documents\\GitHub\\staj\\tools\\test_output\\screenshots
  python tarama.py --klasor ... --ornek 3 --isci 8 --esik 10

Yarıda kesilirse aynı komutla tekrar çalıştırın; ölçülen görüntüler atlanır.

Çıktılar (--cikti, varsayılan: ./denetim_cikti) - Excel'de açılabilir (; ayraçlı):
  tarama.csv   - her görüntü için ölçümler ve bayraklar
  gruplar.csv  - şablon grupları
  ornekler.csv - AI'ya gönderilecek temsilci görüntüler
  ozet.txt     - genel özet
  tarama_ham.csv - ham ölçümler (devam etmek için önbellek)

Bağımlılık: pip install pillow
"""

import argparse
import csv
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageStat

Image.MAX_IMAGE_PIXELS = None  # tam sayfa görüntüler çok uzun olabilir

HAM_ALANLAR = ["dosya", "genislik", "yukseklik", "bayt", "std", "dh64", "dh256", "hata"]
AD_KALIBI = re.compile(r"^(?P<slug>.*)-(?P<hash>[0-9a-f]{8})__(?P<cihaz>[A-Za-z0-9]+)$")
DETAY_KALIBI = re.compile(r"-n-\d+$")

BOS_STD_ESIGI = 4.0      # gri tonlama std sapması bunun altındaysa sayfa boş/tek renk
KISA_ORAN = 0.3          # medyan yüksekliğin %30'undan kısa
UZUN_ORAN = 5.0          # medyan yüksekliğin 5 katından uzun
KOPYA_MIN_SAYFA = 3      # aynı görünümü paylaşan en az farklı sayfa sayısı
KELIME_MIN = 10          # URL son kelimesinin "sayfa türü" sayılması için en az geçme sayısı
MIN_KUME = 5             # temsilci seçilecek görsel kümenin en az sayfa sayısı


# ------------------------------------------------------------------ ÖLÇÜM (paralel)

def dhash(gray, w, h):
    """Fark hash'i: komşu piksel parlaklık karşılaştırması. w = h + 1."""
    px = gray.resize((w, h), Image.BILINEAR).tobytes()  # "L" modunda piksel başına 1 bayt
    bits = 0
    for r in range(h):
        row = px[r * w:(r + 1) * w]
        for c in range(w - 1):
            bits = (bits << 1) | (row[c] > row[c + 1])
    return bits


def olc(args):
    yol, anahtar = args
    sonuc = {"dosya": anahtar, "bayt": Path(yol).stat().st_size}
    try:
        with Image.open(yol) as im:
            w, h = im.size
            im.thumbnail((256, max(1, 256 * h // max(w, 1))))
            g = im.convert("L")
        sonuc.update({
            "genislik": w,
            "yukseklik": h,
            "std": round(ImageStat.Stat(g).stddev[0], 2),
            "dh64": f"{dhash(g, 9, 8):016x}",
            "dh256": f"{dhash(g, 17, 16):064x}",
            "hata": "",
        })
    except Exception as e:
        sonuc.update({"genislik": 0, "yukseklik": 0, "std": 0,
                      "dh64": "", "dh256": "", "hata": str(e)[:200]})
    return sonuc


def olcumleri_topla(klasor, cikti, isci):
    ham_yol = cikti / "tarama_ham.csv"
    ham = {}
    if ham_yol.exists():
        with open(ham_yol, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                ham[r["dosya"]] = r

    dosyalar = sorted(klasor.rglob("*.png"))
    yapilacak = [(str(p), p.relative_to(klasor).as_posix()) for p in dosyalar]
    yapilacak = [y for y in yapilacak if y[1] not in ham]
    print(f"📁 {len(dosyalar)} görüntü bulundu, {len(ham)} tanesi önceden ölçülmüş, "
          f"{len(yapilacak)} ölçülecek ({isci} işçi)")

    if yapilacak:
        yeni = not ham_yol.exists()
        baslangic = time.time()
        with open(ham_yol, "a", encoding="utf-8-sig", newline="") as f, \
                ProcessPoolExecutor(max_workers=isci) as havuz:
            yazici = csv.DictWriter(f, fieldnames=HAM_ALANLAR, delimiter=";")
            if yeni:
                yazici.writeheader()
            for i, r in enumerate(havuz.map(olc, yapilacak, chunksize=16), 1):
                yazici.writerow(r)
                ham[r["dosya"]] = r
                if i % 250 == 0 or i == len(yapilacak):
                    f.flush()
                    gecen = time.time() - baslangic
                    kalan = gecen / i * (len(yapilacak) - i)
                    print(f"  [{i}/{len(yapilacak)}] ~{kalan / 60:.0f} dk kaldı", flush=True)

    mevcut = {p.relative_to(klasor).as_posix() for p in dosyalar}
    return [r for k, r in ham.items() if k in mevcut]


# ------------------------------------------------------------------ AD ÇÖZÜMLEME & ŞABLON

def adi_coz(dosya):
    kok = Path(dosya).stem
    m = AD_KALIBI.match(kok)
    if not m:
        sayfa, _, cihaz = kok.rpartition("__")
        return {"sayfa": sayfa or kok, "slug_ham": sayfa or kok, "cihaz": cihaz or "?"}
    return {"sayfa": kok.rsplit("__", 1)[0], "slug_ham": m["slug"], "cihaz": m["cihaz"]}


def sablon_anahtari(slug, kesik, kelimeler):
    """URL'den şablon anahtarı. Adı kesik sayfalar için None (görsel benzerlikle atanır)."""
    t = slug.split("-")
    if t[0] not in ("tr", "en"):
        return slug                               # ör. anasayfa
    bolum = t[1] if len(t) > 1 else ""
    if DETAY_KALIBI.search(slug):
        return f"{t[0]}/{bolum}/[detay]"          # haber, duyuru, etkinlik detayları
    if kesik:
        return None                               # sayfa türünü veren son kelime kesilmiş
    if len(t) <= 2:
        return f"{t[0]}/{bolum}"
    return f"{t[0]}/{bolum}/{t[-1] if t[-1] in kelimeler else '[diger]'}"


def hamming(a, b):
    return bin(a ^ b).count("1")


def gorsel_kumeler(uyeler, esik):
    """Açgözlü kümeleme: dh64 Hamming mesafesi eşik altındaysa aynı küme."""
    kumeler = []
    for u in sorted(uyeler, key=lambda x: x["yukseklik"]):
        for merkez, liste in kumeler:
            if hamming(merkez, u["dh64i"]) <= esik:
                liste.append(u)
                break
        else:
            kumeler.append((u["dh64i"], [u]))
    return sorted((liste for _, liste in kumeler), key=len, reverse=True)


# ------------------------------------------------------------------ ANALİZ

def analiz(satirlar, klasor, ornek_sayisi, esik):
    for r in satirlar:
        r.update(adi_coz(r["dosya"]))
        r["slug"] = r["slug_ham"].rstrip("-")
        for k in ("genislik", "yukseklik", "bayt"):
            r[k] = int(r[k] or 0)
        r["std"] = float(r["std"] or 0)
        r["dh64i"] = int(r["dh64"], 16) if r["dh64"] else 0
        r["dil"] = r["slug"].split("-")[0]
        r["bolum"] = (r["slug"].split("-") + [""])[1]
        r["bayraklar"] = []

    # Dosya adları belli bir uzunlukta kesilmiş olabilir; kesik adlarda sayfa türü kaybolur
    max_slug = max((len(r["slug_ham"]) for r in satirlar), default=0)
    for r in satirlar:
        r["kesik_ad"] = len(r["slug_ham"]) >= max_slug - 1 and max_slug > 60

    # Sayfa türü sözlüğü: kesik olmayan adlarda sık geçen son kelimeler (kalite, yonetim, staff...)
    kelimeler = Counter(r["slug"].split("-")[-1] for r in satirlar
                        if not r["kesik_ad"] and not DETAY_KALIBI.search(r["slug"]))
    kelimeler = {k for k, n in kelimeler.items() if n >= KELIME_MIN}
    for r in satirlar:
        r["sablon"] = sablon_anahtari(r["slug"], r["kesik_ad"], kelimeler)
        r["atama"] = "url"

    cihaza_gore = defaultdict(list)
    for r in satirlar:
        if r["hata"]:
            r["bayraklar"].append("BOZUK_DOSYA")
        else:
            cihaza_gore[r["cihaz"]].append(r)

    # Cihaz başına beklenen genişlik (en sık görülen) ve medyan yükseklik
    istatistik = {}
    for cihaz, liste in cihaza_gore.items():
        mod_w = Counter(r["genislik"] for r in liste).most_common(1)[0][0]
        med_h = statistics.median(r["yukseklik"] for r in liste)
        istatistik[cihaz] = {"mod_genislik": mod_w, "medyan_yukseklik": med_h,
                             "adet": len(liste)}
        for r in liste:
            if r["genislik"] > mod_w:
                r["bayraklar"].append(f"TASMA(+{r['genislik'] - mod_w}px)")
            elif r["genislik"] < mod_w:
                r["bayraklar"].append(f"DAR(-{mod_w - r['genislik']}px)")
            if r["std"] < BOS_STD_ESIGI:
                r["bayraklar"].append("BOS_SAYFA")
            if r["yukseklik"] < med_h * KISA_ORAN:
                r["bayraklar"].append("COK_KISA")
            if r["yukseklik"] > med_h * UZUN_ORAN:
                r["bayraklar"].append("COK_UZUN")

    # Eksik masaüstü/mobil eşi
    cihazlar = sorted(istatistik)
    sayfalar = defaultdict(dict)
    for r in satirlar:
        sayfalar[r["sayfa"]][r["cihaz"]] = r
    eksik_esler = []
    for sayfa, d in sayfalar.items():
        eksik = [c for c in cihazlar if c not in d]
        if eksik:
            eksik_esler.append((sayfa, eksik))
            for r in d.values():
                r["bayraklar"].append("EKSIK_ES(" + ",".join(eksik) + ")")

    # Farklı sayfalarda birebir aynı görünüm (dh256 + cihaz aynı)
    kovalar = defaultdict(list)
    for r in satirlar:
        if r["dh256"] and "BOS_SAYFA" not in r["bayraklar"]:
            kovalar[(r["cihaz"], r["dh256"])].append(r)
    kopya_gruplari = []
    for (cihaz, _), liste in kovalar.items():
        if len({r["sayfa"] for r in liste}) >= KOPYA_MIN_SAYFA:
            kopya_gruplari.append((cihaz, liste))
            for r in liste:
                r["bayraklar"].append(f"AYNI_GORUNUM({len(liste)})")
    kopya_gruplari.sort(key=lambda x: len(x[1]), reverse=True)

    # Şablon grupları: önce URL'den türü belli sayfalar, sonra kesik adlılar görsel benzerlikle
    ana_cihaz = "desktop" if "desktop" in istatistik else (cihazlar[0] if cihazlar else "")
    uygun = lambda r: (r["cihaz"] == ana_cihaz and not r["hata"]
                       and "BOS_SAYFA" not in r["bayraklar"])

    merkezler = defaultdict(list)                 # (dil, bölüm) -> [(dh64, şablon)]
    url_gruplari = defaultdict(list)
    for r in satirlar:
        if r["sablon"] and uygun(r):
            url_gruplari[r["sablon"]].append(r)
    for sablon, uyeler in url_gruplari.items():
        for k in gorsel_kumeler(uyeler, esik):
            merkezler[(k[0]["dil"], k[0]["bolum"])].append((k[0]["dh64i"], sablon))

    for r in satirlar:
        if r["sablon"] is not None or r["cihaz"] != ana_cihaz:
            continue
        adaylar = merkezler.get((r["dil"], r["bolum"]), [])
        mesafe, sablon = min(((hamming(m, r["dh64i"]), s) for m, s in adaylar),
                             default=(99, None))
        if sablon and mesafe <= esik and not r["hata"]:
            r["sablon"], r["atama"] = sablon, f"gorsel({mesafe})"
        else:
            r["sablon"], r["atama"] = f"{r['dil']}/{r['bolum']}/[kesik]", "yok"
    for d in sayfalar.values():                   # diğer cihazlar ana cihazın şablonunu alır
        ana = d.get(ana_cihaz)
        for r in d.values():
            if r["sablon"] is None:
                r["sablon"] = ana["sablon"] if ana else f"{r['dil']}/{r['bolum']}/[kesik]"
                r["atama"] = ana["atama"] if ana else "yok"

    gruplar = defaultdict(list)
    for r in satirlar:
        gruplar[r["sablon"]].append(r)

    # Temsilci seçimi: her şablonda en az MIN_KUME sayfalık görsel kümelerin ortanca sayfası
    # (en fazla ornek_sayisi küme); hiç büyük küme yoksa en büyük kümeden bir sayfa.
    # Taşma bayraklı grupta en çok taşan sayfa da eklenir.
    ornekler, grup_satirlari = [], []
    for sablon, uyeler in gruplar.items():
        adaylar = [r for r in uyeler if uygun(r)] or [r for r in uyeler if not r["hata"]]
        kumeler = gorsel_kumeler(adaylar, esik) if adaylar else []
        secilecek = [k for k in kumeler if len(k) >= MIN_KUME][:ornek_sayisi] or kumeler[:1]

        secilen = {}
        for i, k in enumerate(secilecek, 1):
            orta = sorted(k, key=lambda x: x["yukseklik"])[len(k) // 2]
            secilen.setdefault(orta["sayfa"], f"görsel küme {i} ({len(k)} sayfa)")
        tasanlar = [r for r in uyeler if any(b.startswith("TASMA") for b in r["bayraklar"])]
        if tasanlar:
            en_cok = max(tasanlar, key=lambda x: x["genislik"])
            secilen.setdefault(en_cok["sayfa"], f"en çok taşan sayfa ({len(tasanlar)} taşma)")

        for sayfa, neden in secilen.items():
            for cihaz, r in sorted(sayfalar[sayfa].items()):
                ornekler.append({
                    "dosya": r["dosya"], "tam_yol": str(klasor / r["dosya"]),
                    "sayfa": sayfa, "cihaz": cihaz, "sablon": sablon,
                    "grup_sayfa_sayisi": len({u["sayfa"] for u in uyeler}), "neden": neden,
                })

        grup_satirlari.append({
            "sablon": sablon,
            "sayfa_sayisi": len({u["sayfa"] for u in uyeler}),
            "gorsel_kume_sayisi": len(kumeler),
            "secilen_sayfa": len(secilen),
            "bayrakli_goruntu": sum(1 for u in uyeler if u["bayraklar"]),
            "ornek_sayfa": uyeler[0]["sayfa"],
        })
    grup_satirlari.sort(key=lambda g: g["sayfa_sayisi"], reverse=True)

    return {"istatistik": istatistik, "eksik_esler": eksik_esler,
            "kopya_gruplari": kopya_gruplari, "gruplar": grup_satirlari,
            "ornekler": ornekler}


# ------------------------------------------------------------------ ÇIKTI

def csv_yaz(yol, satirlar, alanlar):
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=alanlar, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(satirlar)


def ciktilari_yaz(cikti, satirlar, s):
    for r in satirlar:
        r["bayraklar_str"] = " ".join(r["bayraklar"])
    csv_yaz(cikti / "tarama.csv", sorted(satirlar, key=lambda r: r["dosya"]),
            ["dosya", "sayfa", "dil", "bolum", "cihaz", "sablon", "genislik", "yukseklik",
             "bayt", "std", "kesik_ad", "atama", "bayraklar_str"])
    csv_yaz(cikti / "gruplar.csv", s["gruplar"],
            ["sablon", "sayfa_sayisi", "gorsel_kume_sayisi", "secilen_sayfa",
             "bayrakli_goruntu", "ornek_sayfa"])
    csv_yaz(cikti / "ornekler.csv", s["ornekler"],
            ["dosya", "tam_yol", "sayfa", "cihaz", "sablon", "grup_sayfa_sayisi", "neden"])

    bayrak_sayim = Counter()
    for r in satirlar:
        for b in r["bayraklar"]:
            bayrak_sayim[(r["cihaz"], b.split("(")[0])] += 1

    L = ["=" * 70, "GÖRSEL DENETİM - AŞAMA 1 ÖZETİ", "=" * 70, ""]
    L.append(f"Toplam görüntü: {len(satirlar)}")
    L.append(f"Toplam sayfa  : {len({r['sayfa'] for r in satirlar})}")
    L.append("")
    L.append("CİHAZLAR")
    for c, i in sorted(s["istatistik"].items()):
        L.append(f"  {c:10s} {i['adet']:6d} görüntü | beklenen genişlik {i['mod_genislik']} px"
                 f" | medyan yükseklik {i['medyan_yukseklik']:.0f} px")
    L.append("")
    L.append("KOD İLE BULUNAN BAYRAKLAR (cihaz / bayrak / adet)")
    for (c, b), n in sorted(bayrak_sayim.items(), key=lambda x: -x[1]):
        L.append(f"  {c:10s} {b:15s} {n:6d}")
    if not bayrak_sayim:
        L.append("  (yok)")
    L.append("")
    L.append(f"EKSİK EŞLER ({len(s['eksik_esler'])} sayfa)")
    for sayfa, eksik in s["eksik_esler"][:20]:
        L.append(f"  {sayfa}  -> eksik: {', '.join(eksik)}")
    L.append("")
    L.append(f"AYNI GÖRÜNEN FARKLI SAYFALAR ({len(s['kopya_gruplari'])} küme, ilk 15)")
    L.append("  (soft-404, ana sayfaya yönlendirme veya içeriği boş şablon olabilir - kontrol edin)")
    for cihaz, liste in s["kopya_gruplari"][:15]:
        ornek = ", ".join(sorted({r["sayfa"] for r in liste})[:3])
        L.append(f"  [{cihaz}] {len(liste)} sayfa  örn: {ornek}")
    L.append("")
    L.append(f"ŞABLON GRUPLARI: {len(s['gruplar'])} grup (en büyük 25)")
    for g in s["gruplar"][:25]:
        L.append(f"  {g['sayfa_sayisi']:6d} sayfa | {g['gorsel_kume_sayisi']:4d} küme | "
                 f"{g['secilen_sayfa']:2d} seçildi | {g['sablon']}")
    L.append("")
    tek = sum(1 for g in s["gruplar"] if g["sayfa_sayisi"] == 1)
    L.append(f"Tek sayfalık grup sayısı: {tek}")
    kesik = [r for r in satirlar if r["kesik_ad"] and r["cihaz"] == "desktop"]
    atanan = sum(1 for r in kesik if r["atama"].startswith("gorsel"))
    L.append(f"Adı kesik sayfa: {len(kesik)} | görsel benzerlikle şablona atanan: {atanan}")
    L.append("")
    L.append(f"AI'YA GİDECEK TEMSİLCİ: {len({o['sayfa'] for o in s['ornekler']})} sayfa, "
             f"{len(s['ornekler'])} görüntü (toplamın %"
             f"{100 * len(s['ornekler']) / max(len(satirlar), 1):.1f}'i)")
    metin = "\n".join(L)
    (cikti / "ozet.txt").write_text(metin, encoding="utf-8")
    print("\n" + metin)


def main():
    p = argparse.ArgumentParser(description="Görsel denetim - kod ile tarama ve şablon gruplama")
    p.add_argument("--klasor", required=True, help="Ekran görüntüleri klasörü")
    p.add_argument("--cikti", default="denetim_cikti", help="Çıktı klasörü")
    p.add_argument("--ornek", type=int, default=3,
                   help="Şablon başına en fazla kaç görsel kümeden örnek alınsın (vars. 3)")
    p.add_argument("--esik", type=int, default=10,
                   help="Görsel benzerlik eşiği, 64 bit Hamming (vars. 10; küçük = daha çok küme)")
    p.add_argument("--isci", type=int, default=6, help="Paralel işçi sayısı (vars. 6)")
    a = p.parse_args()

    klasor = Path(a.klasor).resolve()
    if not klasor.is_dir():
        sys.exit(f"Klasör bulunamadı: {klasor}")
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)

    satirlar = olcumleri_topla(klasor, cikti, a.isci)
    if not satirlar:
        sys.exit("Hiç görüntü bulunamadı.")
    sonuc = analiz(satirlar, klasor, a.ornek, a.esik)
    ciktilari_yaz(cikti, satirlar, sonuc)
    print(f"\n💾 Çıktılar: {cikti.resolve()}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
