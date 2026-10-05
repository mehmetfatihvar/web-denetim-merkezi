#!/usr/bin/env python3
"""
Görsel Denetim - Son Rapor (HTML)

Bütün aşamaların çıktılarını tek bir HTML raporda toplar:
  - Kodla kesinleşen bulgular (tarama.csv: taşma, eksik eş, aynı görünüm;
    http_hatali.csv: 404/403)
  - Metin kodlama hataları (metin_kontrol.csv)
  - Yapay zeka bulguları (ai_v2/sonuclar.jsonl): isabeti yeterli türlerde 2+ modelin
    aynı dilimde bulduğu hatalar ekran görüntüsü kesitleriyle; tek modelli bulgular
    'inceleme önerilir' olarak; isabeti düşük türler yalnızca sayı olarak
  - Yapay zeka isabet tablosu ve taşma için piksel ölçümüyle karşılaştırma
  - Yöntem ve sınırlamalar

Kullanım (tools/visual_audit içinden):
  python rapor.py
  python rapor.py --ai denetim_cikti/ai_v2 --klasor ../yeniden_cekim/screenshots

Çıktı: denetim_cikti/rapor/rapor.html (+ kesitler/ klasörü)
"""

import argparse
import csv
import hashlib
import html
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

GUVENILIR = {"mojibake", "overlap", "missing_data", "broken_image"}   # isabet ölçümüne göre
TUR_ADI = {
    "horizontal_overflow": "Yatay taşma", "overlap": "Üst üste binme",
    "cut_off_text": "Kesik metin", "broken_image": "Bozuk / eksik görsel",
    "misalignment": "Hizasızlık", "low_contrast": "Düşük kontrast",
    "mojibake": "Bozuk Türkçe karakter", "empty_gap": "Boş alan",
    "broken_navigation": "Bozuk menü", "missing_data": "Eksik veri / boş içerik", "other": "Diğer",
}
E = html.escape


def sayi(n):
    """Türkçe binlik ayırıcı: 34786 -> 34.786"""
    return f"{n:,}".replace(",", ".")


def csv_oku(yol):
    yol = Path(yol)
    if not yol.exists():
        return []
    with open(yol, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def ai_kayitlari(yol):
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
    return [r for r in son.values() if not r.get("hata") and r.get("cevap")]


def kesit(klasor, kayit, hedef):
    """Dilimin ekran görüntüsü kesitini JPEG olarak kaydeder, göreli yolunu döner."""
    kaynak = Path(klasor) / Path(kayit["dosya"]).name
    if not kaynak.exists():
        return ""
    ad = hashlib.md5(f"{kayit['dosya']}#{kayit['dilim']}".encode()).hexdigest()[:12] + ".jpg"
    cikti = hedef / ad
    if not cikti.exists():
        try:
            with Image.open(kaynak) as im:
                im = im.convert("RGB")
                y0, y1 = int(kayit.get("y0", 0)), int(kayit.get("y1", im.height))
                parca = im.crop((0, max(0, y0), im.width, min(im.height, max(y1, y0 + 1))))
                w = min(700, parca.width)
                parca = parca.resize((w, max(1, round(parca.height * w / parca.width))))
                parca.save(cikti, "JPEG", quality=80)
        except Exception:
            return ""
    return f"kesitler/{ad}"


def tablo(basliklar, satirlar, sinif=""):
    t = [f'<table class="{sinif}"><thead><tr>' + "".join(f"<th>{E(b)}</th>" for b in basliklar)
         + "</tr></thead><tbody>"]
    for s in satirlar:
        t.append("<tr>" + "".join(f"<td>{h}</td>" for h in s) + "</tr>")
    t.append("</tbody></table>")
    return "".join(t)


def main():
    p = argparse.ArgumentParser(description="Görsel denetim son raporu")
    p.add_argument("--tarama", default="denetim_cikti/tarama.csv")
    p.add_argument("--ai", default="denetim_cikti/ai_v2")
    p.add_argument("--ana", default="gemini:gemma-4-31b-it")
    p.add_argument("--klasor", default="../yeniden_cekim/screenshots")
    p.add_argument("--http", default="../yeniden_cekim/http_hatali.csv")
    p.add_argument("--metin", default="metin_kontrol.csv")
    p.add_argument("--cikti", default="denetim_cikti/rapor")
    p.add_argument("--site-adi", default="MEÜ ÖİDB web sitesi ön-prodüksiyon ortamı",
                   help="Rapor başlığının altında görünecek site adı")
    p.add_argument("--kesit-limit", type=int, default=80, help="Görselli KESİN bulgu sayısı")
    a = p.parse_args()

    cikti = Path(a.cikti)
    (cikti / "kesitler").mkdir(parents=True, exist_ok=True)

    # ---------------- kod taraması
    tarama = csv_oku(a.tarama)
    sayfa_sayisi = len({r["sayfa"] for r in tarama})
    bayrak = lambda r, b: b in r.get("bayraklar_str", "")
    tasan = [r for r in tarama if bayrak(r, "TASMA")]
    for r in tasan:
        try:
            r["_px"] = int(r["bayraklar_str"].split("TASMA(+")[1].split("px")[0])
        except (IndexError, ValueError):
            r["_px"] = 0
    eksik = [r for r in tarama if bayrak(r, "EKSIK_ES")]
    ayni = [r for r in tarama if bayrak(r, "AYNI_GORUNUM")]
    http_hata = csv_oku(a.http)
    metin = [r for r in csv_oku(a.metin) if r.get("desen")]

    # ---------------- yapay zeka
    kayitlar = ai_kayitlari(Path(a.ai) / "sonuclar.jsonl")
    modeller = sorted({r["model"] for r in kayitlar})
    dilim_bulgu = defaultdict(lambda: defaultdict(list))   # (dosya, dilim) -> tür -> [(model, d)]
    dilim_kayit = {}
    for r in kayitlar:
        k = (r["dosya"], r["dilim"])
        dilim_kayit.setdefault(k, r)
        for d in r["cevap"].get("defects", []):
            dilim_bulgu[k][d.get("type", "other")].append((r["model"], d))
    kesin, tek = [], []
    tur_sayim = Counter()
    for k, turler in dilim_bulgu.items():
        for tur, liste in turler.items():
            tur_sayim[tur] += 1
            mods = {m for m, _ in liste}
            if tur in GUVENILIR:
                (kesin if len(mods) >= 2 else tek).append((k, tur, liste))
    kesin.sort(key=lambda x: (x[1], x[0]))

    # taşma: AI vs piksel ölçümü
    tasan_dosya = {r["dosya"] for r in tasan}
    olculen = {r["dosya"] for r in tarama}
    ai_tasma = defaultdict(bool)
    for r in kayitlar:
        if r["model"] == a.ana:
            ai_tasma[r["dosya"]] |= any(d.get("type") == "horizontal_overflow"
                                        for d in r["cevap"].get("defects", []))
    ortak = [d for d in ai_tasma if d in olculen]
    tp = sum(1 for d in ortak if ai_tasma[d] and d in tasan_dosya)
    fp = sum(1 for d in ortak if ai_tasma[d] and d not in tasan_dosya)
    fn = sum(1 for d in ortak if not ai_tasma[d] and d in tasan_dosya)
    isabet = csv_oku(Path(a.ai) / "isabet.csv")

    # ---------------- HTML
    H = []
    kart = lambda sayi, etiket: f'<div class="kart"><b>{sayi}</b><span>{E(etiket)}</span></div>'
    H.append(f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Görsel Denetim Raporu</title><style>
body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 64px}}
h1{{margin:0 0 4px}} h2{{margin-top:40px;border-bottom:2px solid #dde1e7;padding-bottom:6px}}
.alt{{color:#5b6475}} .kartlar{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}}
.kart{{background:#fff;border:1px solid #dde1e7;border-radius:10px;padding:14px}}
.kart b{{display:block;font-size:26px}} .kart span{{color:#5b6475;font-size:13px}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:14px;margin:12px 0}}
th,td{{border:1px solid #dde1e7;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#eef1f5}} td.url{{word-break:break-all;font-size:12px}}
.bulgu{{background:#fff;border:1px solid #dde1e7;border-radius:10px;padding:14px;margin:14px 0}}
.bulgu img{{max-width:100%;max-height:520px;object-fit:contain;object-position:left top;border:1px solid #ccd;margin-top:8px}}
.etiket{{display:inline-block;background:#e8eefc;border-radius:6px;padding:2px 8px;font-size:12px;margin-right:6px}}
.kesin{{background:#d9f2e3}} .not{{background:#fff8e1;border-left:4px solid #f0b400;padding:10px 14px}}
code{{background:#eef1f5;padding:1px 4px;border-radius:4px}}
</style></head><body><main>
<h1>Görsel Denetim Raporu</h1>
<div class="alt">{E(a.site_adi)} · {date.today().isoformat()}</div>
<div class="kartlar">
{kart(sayi(len(tarama)), "ekran görüntüsü kodla tarandı")}
{kart(sayi(sayfa_sayisi), "sayfa (masaüstü + mobil)")}
{kart(len({r['dosya'] for r in kayitlar}), "temsilci görüntü yapay zekaya soruldu")}
{kart(len(tasan), "görüntüde yatay taşma (piksel ölçümü)")}
{kart(len(http_hata), "sayfa 404/403 döndü")}
{kart(len({r['url'] for r in metin}), "sayfada metin kodlama hatası")}
{kart(len({(dilim_kayit[k]["sayfa"], t) for k, t, _ in kesin}), "KESİN yapay zeka bulgusu (sayfa-hata, 2+ model)")}
</div>""")

    H.append(f"""<h2>1. Yöntem</h2><ol>
<li><b>Kod taraması:</b> {sayi(len(tarama))} ekran görüntüsünün hepsi piksel düzeyinde ölçüldü (genişlik, boş sayfa,
anormal boy, eksik masaüstü/mobil eşi, birebir aynı görünen sayfalar). Sayfalar URL kalıbı ve görsel
benzerliğe göre şablon gruplarına ayrıldı ve her gruptan temsilci seçildi.</li>
<li><b>Yeniden çekim:</b> Aşağı kaydırınca yüklenen görseller ve sayaç animasyonları ilk çekimde boş
çıktığı için temsilci sayfalar, sayfa sona kadar kaydırılarak yeniden çekildi.</li>
<li><b>Yapay zeka:</b> Her görüntü dilimlere bölünüp aynı talimat ve JSON şemasıyla modele soruldu.
Ana tarama Gemma 4 31B ile yapıldı; Gemini Flash Lite modelleri hata türü başına rastgele örneklemde
hakemlik yaptı ve ana modelin bakamadığı dilimleri inceledi.</li>
<li><b>Doğrulama:</b> Hata türü başına isabet ölçüldü; taşma bulguları piksel ölçümüyle karşılaştırıldı;
yapay zekanın bulduğu metin kodlama hataları kodla bütün temsilci sayfalarda arandı.</li></ol>""")

    # isabet
    H.append("<h2>2. Yapay zeka isabeti</h2>")
    if isabet:
        H.append("<p>Hakem modelin, ana modelin bulgusunu aynı dilimde aynı türle onaylama oranı "
                 "(rastgele örneklem). Hakem de hata yapabildiği için bu oranlar alt sınır olarak "
                 "okunmalıdır.</p>")
        H.append(tablo(["Cihaz", "Hata türü", "Ana model bulgusu", "Örneklem", "Onay", "İsabet"],
                       [[E(r["cihaz"]), E(TUR_ADI.get(r["tur"], r["tur"])), r["ana_bulgu"],
                         r["ornek"], r["onay"], E(r["isabet"] or "-")] for r in isabet]))
    if tp + fp:
        H.append(f"""<p><b>Taşma: yapay zeka ve piksel ölçümü.</b> {len(ortak)} görüntüde karşılaştırıldı.
Ana model gerçek taşmaların <b>%{100 * tp / max(tp + fn, 1):.0f}</b>'ini buldu (yakalama), ancak
"taşıyor" dediği görüntülerin yalnızca <b>%{100 * tp / (tp + fp):.0f}</b>'i gerçekten taşıyordu (isabet).
Doğru: {tp} · yanlış alarm: {fp} · kaçırılan: {fn}. <b>Sonuç:</b> ölçülebilir hatalar (taşma, boş sayfa)
için yapay zeka yerine kod kullanılmalıdır.</p>""")

    # kod bulguları
    H.append("<h2>3. Kodla kesinleşen bulgular</h2>")
    H.append(f"<h3>3.1 Yatay taşma ({len(tasan)} görüntü)</h3>")
    cihaz_say = Counter(r["cihaz"] for r in tasan)
    H.append("<p>" + " · ".join(f"{E(c)}: {n}" for c, n in cihaz_say.most_common()) +
             ". Sayfa ekran genişliğinden geniş; kullanıcı yatay kaydırmak zorunda kalıyor.</p>")
    sablon_say = Counter((r["sablon"], r["cihaz"]) for r in tasan)
    H.append(tablo(["Şablon", "Cihaz", "Taşan görüntü"],
                   [[E(s), E(c), n] for (s, c), n in sablon_say.most_common(20)]))
    H.append("<p>En çok taşan 20 görüntü:</p>")
    H.append(tablo(["Sayfa", "Cihaz", "Taşma"],
                   [[f'<span class="url">{E(r["sayfa"])}</span>', E(r["cihaz"]), f'+{r["_px"]} px']
                    for r in sorted(tasan, key=lambda x: -x["_px"])[:20]]))
    H.append(f"<h3>3.2 Hata dönen sayfalar ({len(http_hata)})</h3>")
    if http_hata:
        H.append(tablo(["HTTP", "Adres"], [[E(r["http_durum"]), f'<span class="url">{E(r["url"])}</span>']
                                           for r in http_hata]))
    H.append(f"<h3>3.3 Diğer</h3><ul><li>Masaüstü veya mobil ekran görüntüsü eksik: "
             f"{len({r['sayfa'] for r in eksik})} sayfa</li><li>Farklı adreslerde birebir aynı görünen "
             f"görüntü: {len(ayni)} (hata sayfası, yönlendirme veya çalışmayan sayfalama olabilir)</li></ul>")

    # metin
    H.append(f"<h2>4. Metin kodlama hataları ({len({r['url'] for r in metin})} sayfa)</h2>")
    if metin:
        H.append("<p>Yapay zeka incelemesinde fark edilen bu hata sınıfı, sayfaların görünen metninde "
                 "kodla arandı. <code>soru_isareti</code>: Türkçe karakter '?' ile değişmiş "
                 "(ör. Atat?rk); <code>html_kodu</code>: HTML kodu ekrana basılıyor (ör. &amp;#39;); "
                 "<code>html_etiketi</code>: HTML etiketi metin olarak görünüyor (ör. &lt;span class=...&gt;).</p>")
        desen_say = Counter(r["desen"] for r in metin)
        H.append("<p>" + " · ".join(f"{E(d)}: {n} sayfa" for d, n in desen_say.most_common()) + "</p>")
        H.append(tablo(["Adres", "Desen", "Adet", "Örnek"],
                       [[f'<span class="url">{E(r["url"])}</span>', E(r["desen"]), r["adet"],
                         E(r["ornek1"])] for r in metin[:60]]))
    else:
        H.append("<p class='not'>metin_kontrol.csv bulunamadı; <code>python metin_kontrol.py</code> "
                 "çalıştırılıp rapor yeniden üretilmeli.</p>")

    # AI bulguları
    H.append(f"<h2>5. Yapay zeka bulguları</h2><p>Modeller: {E(', '.join(modeller))}. Yalnızca isabeti "
             f"yeterli türler ({E(', '.join(TUR_ADI[t] for t in sorted(GUVENILIR)))}) ayrıntılı "
             "gösterilir.</p>")
    # Aynı sayfadaki aynı hata (masaüstü/mobil, farklı dilimler) tek kartta toplanır
    gruplu = defaultdict(list)
    for (dosya, dilim), tur, liste in kesin:
        gruplu[(dilim_kayit[(dosya, dilim)]["sayfa"], tur)].append(((dosya, dilim), liste))
    H.append(f"<h3>5.1 KESİN: iki veya daha fazla modelin aynı dilimde bulduğu "
             f"({len(gruplu)} sayfa-hata, {len(kesin)} dilim)</h3>")
    for i, ((sayfa, tur), oge) in enumerate(sorted(gruplu.items(), key=lambda x: (x[0][1], x[0][0]))):
        if i >= a.kesit_limit:
            H.append(f"<p>... ve {len(gruplu) - a.kesit_limit} sayfa-hata daha (oylama.csv).</p>")
            break
        (ilk_dosya, ilk_dilim), ilk_liste = oge[0]
        r = dilim_kayit[(ilk_dosya, ilk_dilim)]
        img = kesit(a.klasor, r, cikti / "kesitler")
        yerler = ", ".join(f"{dilim_kayit[k]['cihaz']} #{k[1]}" for k, _ in oge)
        aciklamalar = "".join(
            f"<li><b>{E(m.split(':')[-1])}</b>: {E(d.get('description', ''))} "
            f"<i>Kanıt:</i> “{E(d.get('evidence_text', ''))}” ({E(d.get('location', ''))})</li>"
            for m, d in ilk_liste)
        H.append(f"""<div class="bulgu"><span class="etiket kesin">{E(TUR_ADI.get(tur, tur))}</span>
<span class="etiket">{E(yerler)}</span>
<div class="url">{E(sayfa)}</div><ul>{aciklamalar}</ul>
{f'<img loading="lazy" src="{img}" alt="ekran görüntüsü kesiti ({E(r["cihaz"])} #{ilk_dilim})">' if img else ''}</div>""")

    tek_say = Counter(t for _, t, _ in tek)
    H.append(f"<h3>5.2 Tek modelin bulduğu (inceleme önerilir): {len(tek)}</h3><p>" +
             " · ".join(f"{E(TUR_ADI.get(t, t))}: {n}" for t, n in tek_say.most_common()) + "</p>")
    dusuk = {t: n for t, n in tur_sayim.items() if t not in GUVENILIR}
    H.append("<h3>5.3 İsabeti düşük türler (yalnızca sayı)</h3><p>" +
             " · ".join(f"{E(TUR_ADI.get(t, t))}: {n}" for t, n in sorted(dusuk.items(), key=lambda x: -x[1])) +
             ". Bu türlerde hakem onayı %0-15 arasında kaldı; bulgular ayrı ayrı güvenilir değildir. "
             "Taşma için piksel ölçümü (bölüm 3.1) kullanılmalıdır.</p>")

    H.append("""<h2>6. Sınırlamalar</h2><ul>
<li>Yapay zeka yalnızca temsilci sayfalara (şablon başına 1-4 sayfa) bakmıştır; içerikten kaynaklanan,
tek sayfaya özgü görsel hatalar kaçmış olabilir. Ölçülebilir hatalar (taşma, boş sayfa, HTTP) ise
bütün sayfalarda kodla kontrol edilmiştir.</li>
<li>Hakem onay oranları kesin isabet değil alt sınırdır; iki model de aynı hatayı yapabilir.</li>
<li>Ana modelin teknik hata nedeniyle bakamadığı dilimlere yalnızca tek bir model bakmıştır.</li>
<li>Mobil ana sayfadaki kayan şeritte yer alan sayaçlar, görüntü anında tetiklenmediği için 0
görünebilir; bu bir ekran görüntüsü sınırlamasıdır.</li>
<li>Ücretsiz model kotaları nedeniyle her dilim her modele sorulamamıştır.</li></ul>
</main></body></html>""")

    (cikti / "rapor.html").write_text("\n".join(H), encoding="utf-8")
    print(f"✅ Rapor: {(cikti / 'rapor.html').resolve()}")
    print(f"   KESİN: {len(gruplu)} sayfa-hata ({len(kesin)} dilim) | tek model (güvenilir tür): {len(tek)} | "
          f"taşma: {len(tasan)} | HTTP: {len(http_hata)} | metin: {len({r['url'] for r in metin})} sayfa")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
