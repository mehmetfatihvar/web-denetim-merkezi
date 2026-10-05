#!/usr/bin/env python3
"""
Görsel Denetim - Aşama 7: Bulguların canlı sitede doğrulanması

Önceki aşamaların ekran görüntüsünden bulduğu hataları sayfanın kendisinde (DOM)
yeniden kontrol eder. Böylece her bulgu için "hata hâlâ var mı, çekimden mi
kaynaklandı?" sorusu cevaplanır ve taşmalarda hatayı üreten HTML öğesi (CSS
seçicisi) bulunur. Aynı seçici birçok sayfada çıkıyorsa tek bir CSS düzeltmesi
hepsini giderir (kok_neden.csv).

İki adımda çalışır:

  1) hazirla : hata bulunan sayfaları toplar, URL listesini yazar
       python dogrulama.py hazirla --harita ..\\data\\final_complete_site_map.json

  Sonra çekim aracı bu sayfalarda DOM denetimiyle çalıştırılır:
       python ..\\cekim\\tester.py --source dogrulama_cikti\\dogrulama_urls.json ^
              --out-dir ..\\dogrulama --check-visual --kaydir --fresh
  Metin hataları için (isteğe bağlı):
       python metin_kontrol.py --source dogrulama_cikti\\dogrulama_urls.json ^
              --cikti dogrulama_cikti\\metin_yeniden.csv

  2) karsilastir : eski bulguları yeni ölçümle karşılaştırır
       python dogrulama.py karsilastir

Bulgu kaynakları (bulunanlar kullanılır):
  - tarama.csv      : kodla ölçülen yatay taşma (TASMA)
  - ai_v2/sonuclar.jsonl : 2+ modelin aynı dilimde bulduğu hatalar (KESİN)
  - metin_kontrol.csv    : görünen metindeki kodlama hataları
  - http_hatali.csv      : 200 dönmeyen sayfalar

Karar:
  DOGRULANDI  : aynı hata türü aynı cihazda (AI bulgusunda aynı dikey bölgede) yeniden ölçüldü;
                taşmada ayrıca sayfanın kendisi yana kayıyor
  GORULMEDI   : sayfa açıldı ama hata ölçülmedi (düzeltilmiş ya da çekim kaynaklı); taşmada
                öğe taşıyor ama sayfa yana kaymıyorsa (kendi kutusunda kayan tablo vb.) da buraya düşer
  ELLE        : DOM ile ölçülemeyen tür (üst üste binme, eksik veri…); işaretli görüntüye bakılmalı
  ACILAMADI   : sayfa yeniden açılamadı / doğrulama çekiminde yok

Çıktı: dogrulama_cikti/{dogrulama_urls.json, bekleyen.csv, sonuc.csv, kok_neden.csv, ozet.txt}
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from temsilci_urls import harita_urlleri, safe_name

# AI hata türü -> tester'ın DOM denetim türü (ölçülebilenler)
DOM_TURU = {
    "horizontal_overflow": "icerik_tasmasi",
    "broken_image": "kirik_gorsel",
    "cut_off_text": "metin_kirpma",
}
CIHAZ = {"desktop": "desktop", "mobile": "mobile"}
PAY = 200   # AI dilim sınırına göre dikey tolerans (px)
ALANLAR = ["kaynak", "tur", "cihaz", "url", "sayfa", "dilim", "y0", "y1", "eski_kanit"]


def csv_oku(yol):
    yol = Path(yol)
    if not yol.exists():
        return []
    with open(yol, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def csv_yaz(yol, satirlar, alanlar):
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=alanlar, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(satirlar)


def ad_coz(dosya):
    """'<sayfa>__<cihaz>.png' -> (sayfa, cihaz)"""
    kok = Path(dosya).stem
    sayfa, _, cihaz = kok.rpartition("__")
    return (sayfa or kok), cihaz


def kesin_ai_bulgulari(yol):
    """sonuclar.jsonl -> 2+ modelin aynı dilimde aynı türde bulduğu hatalar."""
    son = {}
    if not Path(yol).exists():
        return []
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            try:
                r = json.loads(satir)
            except json.JSONDecodeError:
                continue
            k = (r["model"], r["dosya"], r["dilim"])
            if not r.get("hata") or k not in son:
                son[k] = r
    oy = defaultdict(lambda: {"modeller": set(), "r": None, "kanit": ""})
    for r in son.values():
        if r.get("hata") or not r.get("cevap"):
            continue
        for d in r["cevap"].get("defects", []):
            k = (r["dosya"], r["dilim"], d.get("type"))
            oy[k]["modeller"].add(r["model"])
            oy[k]["r"] = r
            oy[k]["kanit"] = oy[k]["kanit"] or (d.get("evidence_text") or d.get("description") or "")
    bulgular = []
    for (dosya, dilim, tur), v in oy.items():
        if len(v["modeller"]) < 2:
            continue
        r = v["r"]
        sayfa, cihaz = ad_coz(dosya)
        bulgular.append({"kaynak": "ai_kesin", "tur": tur, "cihaz": r.get("cihaz") or cihaz,
                         "sayfa": r.get("sayfa") or sayfa, "dilim": dilim,
                         "y0": r.get("y0", ""), "y1": r.get("y1", ""),
                         "eski_kanit": v["kanit"][:200]})
    return bulgular


def hazirla(a):
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    ad_url = {}
    for u in harita_urlleri(a.harita):
        if isinstance(u, str) and u.startswith("http"):
            ad_url.setdefault(safe_name(u), u)

    bulgular = []
    for r in csv_oku(a.tarama):
        if "TASMA" in r.get("bayraklar_str", ""):
            sayfa, cihaz = ad_coz(r["dosya"])
            bulgular.append({"kaynak": "kod_tasma", "tur": "horizontal_overflow", "cihaz": cihaz,
                             "sayfa": sayfa, "eski_kanit": r["bayraklar_str"]})
    bulgular += kesin_ai_bulgulari(Path(a.ai) / "sonuclar.jsonl")
    for r in csv_oku(a.metin):
        if r.get("desen"):
            bulgular.append({"kaynak": "metin", "tur": r["desen"], "cihaz": "-", "url": r["url"],
                             "eski_kanit": r.get("ornek1", "")})
    for r in csv_oku(a.http):
        bulgular.append({"kaynak": "http", "tur": f"http_{r['http_durum']}", "cihaz": "-",
                         "url": r["url"], "sayfa": r.get("sayfa", "")})

    eksik = 0
    for b in bulgular:
        if not b.get("url"):
            b["url"] = ad_url.get(b.get("sayfa", ""), "")
            eksik += not b["url"]
    bulgular = [b for b in bulgular if b["url"]]
    urls = list(dict.fromkeys(b["url"] for b in bulgular))

    (cikti / "dogrulama_urls.json").write_text(
        json.dumps({"url_list": urls}, ensure_ascii=False, indent=1), encoding="utf-8")
    csv_yaz(cikti / "bekleyen.csv", bulgular, ALANLAR)
    sayac = Counter(b["kaynak"] for b in bulgular)
    print(f"✅ {len(bulgular)} bulgu, {len(urls)} benzersiz sayfa -> {cikti / 'dogrulama_urls.json'}")
    print("   " + ", ".join(f"{k}: {v}" for k, v in sayac.most_common()))
    if eksik:
        print(f"⚠️  {eksik} bulgunun URL'si haritada bulunamadı, atlandı")
    print("\nSonraki adım:\n  python ..\\cekim\\tester.py --source "
          f"{cikti}\\dogrulama_urls.json --out-dir ..\\dogrulama --check-visual --kaydir --fresh")


def yeni_olcumler(yol):
    olcum = {}
    if not Path(yol).exists():
        sys.exit(f"[HATA] {yol} yok. Önce tester.py --check-visual ile doğrulama çekimini yapın.")
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            try:
                r = json.loads(satir)
            except json.JSONDecodeError:
                continue
            if r.get("url"):
                olcum[r["url"]] = r
    return olcum


def karsilastir(a):
    cikti = Path(a.cikti)
    bekleyen = csv_oku(cikti / "bekleyen.csv")
    if not bekleyen:
        sys.exit(f"[HATA] {cikti / 'bekleyen.csv'} yok ya da boş. Önce 'hazirla' çalıştırın.")
    olcum = yeni_olcumler(Path(a.dogrulama) / "results.jsonl")
    metin_yeni = defaultdict(set)
    metin_var = Path(a.metin_yeni).exists()
    for r in csv_oku(a.metin_yeni):
        if r.get("desen"):
            metin_yeni[r["url"]].add(r["desen"])

    sonuc, kok = [], defaultdict(lambda: {"sayfalar": set(), "max_px": 0, "metin": ""})
    for b in bekleyen:
        r = olcum.get(b["url"])
        karar, ayrinti, kanit = "ACILAMADI", "", ""
        sayfa_kayiyor, kusur_y = "", ""
        if b["kaynak"] == "metin":
            if not metin_var:
                karar, ayrinti = "ELLE", "metin_kontrol yeniden çalıştırılmadı"
            else:
                karar = "DOGRULANDI" if b["tur"] in metin_yeni.get(b["url"], set()) else "GORULMEDI"
        elif r is None:
            pass
        elif b["kaynak"] == "http":
            durum = r.get("http_status")
            karar = "GORULMEDI" if durum == 200 else "DOGRULANDI"
            ayrinti = f"şimdi: {durum}"
        else:
            gorsel = r.get("visual") or {}
            kanit = (r.get("evidence") or {}).get(f"vshot_{b['cihaz']}", "")
            dom_tur = DOM_TURU.get(b["tur"])
            if dom_tur is None:
                karar, ayrinti = "ELLE", "DOM ile ölçülemeyen tür"
            else:
                cihaz = CIHAZ.get(b["cihaz"], b["cihaz"])
                tum = [d for d in gorsel.get(cihaz, []) if d.get("type") == dom_tur]
                kusurlar = tum
                if b["y0"] != "" and b.get("y1"):           # AI bulgusu: aynı dikey bölge
                    y0, y1 = int(b["y0"]) - PAY, int(b["y1"]) + PAY
                    kusurlar = [d for d in tum if (d.get("rect") or {}).get("y") is None
                                or y0 <= d["rect"]["y"] <= y1]
                kayiyor, tasiran = None, None
                if dom_tur == "icerik_tasmasi":
                    olcu = (gorsel.get("sayfa_genislik") or {}).get(cihaz) or {}
                    kayiyor, tasiran = olcu.get("kayiyor"), olcu.get("tasiran")
                    sayfa_kayiyor = {True: "evet", False: "hayir"}.get(kayiyor, "")
                    if tasiran and b["y0"] != "" and b.get("y1") and not (
                            int(b["y0"]) - PAY <= tasiran.get("y", -1) <= int(b["y1"]) + PAY):
                        tasiran = None                  # AI bulgusu: başka bölgede
                if kayiyor and not kusurlar and tasiran:
                    # İçeriksiz kutu / gizli panel sayfayı genişletiyor: içerik denetimi
                    # bunu görmez ama kullanıcı yana kaydırınca boş alan görür.
                    kusurlar = [{"selector": tasiran.get("selector", ""),
                                 "value": f"{tasiran.get('tasma_px', 0)}px tasma",
                                 "text": tasiran.get("metin", ""), "rect": {"y": tasiran.get("y")},
                                 "_genisleten": True}]
                if kusurlar:
                    kusur_y = (kusurlar[0].get("rect") or {}).get("y", "")
                if kayiyor is False:
                    # Taşmanın kullanıcı açısından tanımı sayfanın yana kaymasıdır. Kaymıyorsa
                    # öğe kendi kutusunda kayıyordur ya da hata çekimden kaynaklanmıştır.
                    karar = "GORULMEDI"
                    ayrinti = ("öğe taşıyor ama sayfa yana kaymıyor" if tum
                               else "sayfa yana kaymıyor")
                elif kayiyor and not kusurlar:
                    karar = "ELLE" if not tum else "GORULMEDI"
                    ayrinti = ("sayfa yana kayıyor ama taşan öğe bulunamadı" if not tum
                               else "sayfa kayıyor ama taşma başka bölgede")
                elif kusurlar:
                    karar = "DOGRULANDI"
                    ayrinti = "; ".join(f"{d.get('selector')} ({d.get('value')})" for d in kusurlar[:3])
                    if kusurlar[0].get("_genisleten"):
                        ayrinti = "sayfayı genişleten öğe (içeriksiz/gizli olabilir): " + ayrinti
                    for d in kusurlar:
                        tur_adi = "sayfa_genisleten" if d.get("_genisleten") else dom_tur
                        k = kok[(b["cihaz"], tur_adi, d.get("selector", ""))]
                        k["sayfalar"].add(b["url"])
                        k["metin"] = k["metin"] or d.get("text", "")
                        try:
                            k["max_px"] = max(k["max_px"], int(str(d.get("value", "0")).split("px")[0]))
                        except ValueError:
                            pass
                else:
                    karar = "GORULMEDI"
        sonuc.append({**b, "karar": karar, "ayrinti": ayrinti, "kanit_goruntu": kanit,
                      "sayfa_kayiyor": sayfa_kayiyor, "kusur_y": kusur_y})

    csv_yaz(cikti / "sonuc.csv", sonuc, ["karar"] + ALANLAR +
            ["sayfa_kayiyor", "ayrinti", "kanit_goruntu", "kusur_y"])
    kok_satir = sorted(({"cihaz": c, "tur": t, "secici": s, "sayfa_sayisi": len(v["sayfalar"]),
                         "max_tasma_px": v["max_px"], "ornek_metin": v["metin"],
                         "ornek_url": sorted(v["sayfalar"])[0]}
                        for (c, t, s), v in kok.items()), key=lambda x: -x["sayfa_sayisi"])
    csv_yaz(cikti / "kok_neden.csv", kok_satir,
            ["sayfa_sayisi", "cihaz", "tur", "secici", "max_tasma_px", "ornek_metin", "ornek_url"])

    L = ["=" * 64, "BULGU DOĞRULAMA (canlı sayfada DOM ölçümü)", "=" * 64, ""]
    tablo = defaultdict(Counter)
    for s in sonuc:
        tablo[(s["kaynak"], s["tur"])][s["karar"]] += 1
    kararlar = ["DOGRULANDI", "GORULMEDI", "ELLE", "ACILAMADI"]
    L.append(f"{'kaynak':10s} {'tür':22s} " + " ".join(f"{k[:10]:>10s}" for k in kararlar))
    for (kaynak, tur), c in sorted(tablo.items()):
        L.append(f"{kaynak:10s} {tur[:22]:22s} " + " ".join(f"{c[k]:10d}" for k in kararlar))
    toplam = Counter(s["karar"] for s in sonuc)
    kayma = Counter((s["kaynak"], s["sayfa_kayiyor"]) for s in sonuc if s["sayfa_kayiyor"])
    if kayma:
        L += ["", "Taşma bulgularında sayfa yana kayıyor mu (yanlış alarm ayıklama):"]
        for kaynak in sorted({k for k, _ in kayma}):
            L.append(f"  {kaynak:10s} evet: {kayma[(kaynak, 'evet')]:4d}   "
                     f"hayir (yanlış alarm / düzelmiş): {kayma[(kaynak, 'hayir')]:4d}")
    L += ["", "TOPLAM: " + ", ".join(f"{k}: {toplam[k]}" for k in kararlar), ""]
    if kok_satir:
        L.append("EN ÇOK SAYFAYI ETKİLEYEN ÖĞELER (tek düzeltme, çok sayfa):")
        for k in kok_satir[:15]:
            L.append(f"  {k['sayfa_sayisi']:4d} sayfa  {k['cihaz']:7s} {k['tur']:15s} "
                     f"{k['secici'][:50]:50s} max {k['max_tasma_px']}px")
    metin = "\n".join(L)
    (cikti / "ozet.txt").write_text(metin, encoding="utf-8")
    print(metin)
    print(f"\n💾 {cikti / 'sonuc.csv'}, kok_neden.csv, ozet.txt")


def main():
    p = argparse.ArgumentParser(description="Bulguları canlı sitede doğrula")
    alt = p.add_subparsers(dest="komut", required=True)
    h = alt.add_parser("hazirla", help="Hata bulunan sayfaların URL listesini çıkar")
    h.add_argument("--harita", required=True, help="final_complete_site_map.json yolu")
    h.add_argument("--tarama", default="denetim_cikti/tarama.csv")
    h.add_argument("--ai", default="denetim_cikti/ai_v2")
    h.add_argument("--metin", default="metin_kontrol.csv")
    h.add_argument("--http", default="../yeniden_cekim/http_hatali.csv")
    k = alt.add_parser("karsilastir", help="Eski bulguları yeni ölçümle karşılaştır")
    k.add_argument("--dogrulama", default="../dogrulama", help="tester --out-dir klasörü")
    k.add_argument("--metin-yeni", default="dogrulama_cikti/metin_yeniden.csv")
    for s in (h, k):
        s.add_argument("--cikti", default="dogrulama_cikti")
    a = p.parse_args()
    hazirla(a) if a.komut == "hazirla" else karsilastir(a)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
