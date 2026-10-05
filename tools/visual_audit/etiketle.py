#!/usr/bin/env python3
"""
Görsel Denetim - Aşama 8: Elle etiketleme (yanlış alarm ayıklama)

Üç grup bulgu tek bir HTML sayfada gösterilir:
  ELLE      : kodla ölçülemeyenler (üst üste binme, eksik veri, yapay zekâ mojibake'i…)
  GÖRÜLMEDİ : ölçümün "hata yok" dediği, yani yanlış alarm sayılan bulgular; bu
              kararın kendisi de gözle doğrulanır
  ÖRNEK     : DOGRULANDI bulgulardan rastgele örneklem (otomatik doğrulamanın isabeti)
Her bulgu için bulgunun iddia edildiği eski çekim ve sayfanın şimdiki hali yan yana,
eski kanıt ve üç seçenek: Gerçek / Yanlış / Emin değilim.
Eski çekim klasörü birden fazla verilebilir (ör. ilk tam çekim):
       python etiketle.py olustur --klasor ..\yeniden_cekim\screenshots ..\..\staj\tools\test_output\screenshots

  1) olustur : etiketleme sayfasını üretir
       python etiketle.py olustur
       start etiket\\etiketle.html
     Klavye: 1 = Gerçek, 2 = Yanlış, 3 = Emin değilim, ← → = önceki/sonraki.
     Etiketler tarayıcıda saklanır; bitince "CSV indir" ile etiketler.csv kaydedilir.

  2) ozet : indirilen etiketleri bulgularla birleştirir, tür başına isabeti hesaplar
       python etiketle.py ozet --etiketler %USERPROFILE%\\Downloads\\etiketler.csv

Çıktı: etiket/{etiketle.html, kesitler/, ogeler.csv, etiket_ozet.txt, sonuc_etiketli.csv}
"""

import argparse
import csv
import hashlib
import html
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

from temsilci_urls import safe_name

Image.MAX_IMAGE_PIXELS = None
TUR_ADI = {
    "horizontal_overflow": "Yatay taşma", "overlap": "Üst üste binme",
    "cut_off_text": "Kesik metin", "broken_image": "Bozuk / eksik görsel",
    "misalignment": "Hizasızlık", "low_contrast": "Düşük kontrast",
    "mojibake": "Bozuk Türkçe karakter", "empty_gap": "Boş alan",
    "broken_navigation": "Bozuk menü", "missing_data": "Eksik veri / boş içerik", "other": "Diğer",
    "soru_isareti": "Türkçe karakter yerine ?", "html_kodu": "Ekranda HTML kodu",
}
EKRAN = {"desktop": 1366, "mobile": 375}      # tester.py viewport genişlikleri
ETIKETLER = {"gercek": "Gerçek hata", "yanlis": "Yanlış alarm", "emin_degil": "Emin değilim"}
ALANLAR = ["id", "secim", "otomatik_karar", "kaynak", "tur", "cihaz", "url", "sayfa", "dilim",
           "eski_kanit", "ayrinti", "kesit", "kesit_eski"]


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


def oge_id(s):
    anahtar = "|".join(s.get(k, "") for k in ("kaynak", "tur", "cihaz", "url", "dilim"))
    return hashlib.md5(anahtar.encode("utf-8")).hexdigest()[:12]


def kirp(kaynak, y0, y1, hedef, kenar=None):
    """Görüntünün [y0, y1] bandını 700 px genişliğe küçültüp JPEG kaydeder.
    kenar verilirse (ekran genişliği, px) o hizaya kırmızı dikey çizgi çizilir:
    çizginin sağında kalan her şey ekrana sığmayan, yani taşan kısımdır."""
    try:
        with Image.open(kaynak) as im:
            im = im.convert("RGB")
            y0, y1 = max(0, int(y0)), min(im.height, max(int(y1), int(y0) + 1))
            parca = im.crop((0, y0, im.width, y1))
            if kenar and parca.width > kenar:
                ciz = ImageDraw.Draw(parca)
                ciz.rectangle((kenar, 0, kenar + 2, parca.height), fill=(229, 72, 77))
            w = min(700, parca.width)
            parca = parca.resize((w, max(1, round(parca.height * w / parca.width))))
            parca.save(hedef, "JPEG", quality=82)
        return True
    except Exception:
        return False


def kesit_yeni(s, a, hedef):
    """Doğrulama çekiminden (sayfanın şimdiki hali) görüntü: DOM'da işaretlenmiş
    kusur varsa onun çevresi, yoksa bulgunun bölgesi ya da sayfanın üst kısmı."""
    dogrulama = Path(a.dogrulama)
    if s.get("kanit_goruntu") and s.get("kusur_y") not in ("", None):
        y = int(float(s["kusur_y"]))
        if kirp(dogrulama / s["kanit_goruntu"], y - 300, y + 900, hedef):
            return True
    cihaz = s.get("cihaz") if s.get("cihaz") in ("desktop", "mobile") else "desktop"
    y0, y1 = (s["y0"], s["y1"]) if s.get("y0") not in ("", None) else (0, 1600)
    return kirp(dogrulama / "screenshots" / f"{safe_name(s['url'])}__{cihaz}.png", y0, y1, hedef,
                EKRAN[cihaz])


def kesit_eski(s, a, hedef):
    """Bulgunun iddia edildiği eski çekimden görüntü (yapay zekânın baktığı dilim
    ya da kod taşmasında sayfanın üst kısmı). Klasörler sırayla denenir."""
    if not s.get("sayfa") or s.get("cihaz") not in ("desktop", "mobile"):
        return False
    y0, y1 = (s["y0"], s["y1"]) if s.get("y0") not in ("", None) else (0, 1600)
    return any(kirp(Path(k) / f"{s['sayfa']}__{s['cihaz']}.png", y0, y1, hedef,
                    EKRAN[s["cihaz"]]) for k in a.klasor)


SAYFA = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bulgu Etiketleme</title>
<style>
:root{--bg:#f6f7f9;--fg:#1d2330;--soluk:#5b6475;--kart:#fff;--cizgi:#dde1e8;
 --gercek:#1f8a4c;--yanlis:#c2410c;--emin:#6b7280;--vurgu:#2557d6}
@media (prefers-color-scheme:dark){:root{--bg:#14171d;--fg:#e6e9ef;--soluk:#9aa3b5;--kart:#1c2028;
 --cizgi:#2c323d;--vurgu:#7aa2ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--kart);border-bottom:1px solid var(--cizgi);
 padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:2}
header h1{font-size:16px;margin:0;flex:1}
.ilerleme{height:6px;background:var(--cizgi);border-radius:3px;width:160px;overflow:hidden}
.ilerleme div{height:100%;background:var(--vurgu)}
main{max-width:1200px;margin:0 auto;padding:16px;display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:16px}
@media (max-width:860px){main{grid-template-columns:1fr}}
.gorsel{background:var(--kart);border:1px solid var(--cizgi);border-radius:8px;padding:8px;
 max-height:78vh;overflow:auto;text-align:center}
.gorsel img{max-width:100%;height:auto}
.ikili{display:flex;gap:8px;align-items:flex-start;overflow-x:auto}
.ikili figure{margin:0;flex:0 0 auto}.ikili img{max-width:none}
figcaption{font-size:12px;color:var(--soluk);margin-bottom:4px}
.panel{background:var(--kart);border:1px solid var(--cizgi);border-radius:8px;padding:14px}
.panel dt{color:var(--soluk);font-size:12px;margin-top:8px}
.panel dd{margin:2px 0 0;word-break:break-word}
.rozet{display:inline-block;padding:1px 8px;border-radius:10px;border:1px solid var(--cizgi);font-size:12px}
.butonlar{display:grid;gap:8px;margin-top:14px}
button{font:inherit;padding:10px;border-radius:6px;border:1px solid var(--cizgi);background:var(--kart);
 color:var(--fg);cursor:pointer;text-align:left}
button.secili{outline:3px solid var(--vurgu)}
button[data-e=gercek]{border-left:6px solid var(--gercek)}
button[data-e=yanlis]{border-left:6px solid var(--yanlis)}
button[data-e=emin_degil]{border-left:6px solid var(--emin)}
kbd{border:1px solid var(--cizgi);border-radius:3px;padding:0 5px;font-size:12px}
.gezinme{display:flex;gap:8px;margin-top:10px}
.gezinme button{flex:1;text-align:center}
a{color:var(--vurgu)}
</style></head><body>
<header><h1>Bulgu Etiketleme</h1><span id="sayac"></span>
<div class="ilerleme"><div id="cubuk"></div></div>
<button id="indir">CSV indir</button></header>
<main><div class="gorsel"><div class="ikili">
<figure id="eskiKutu"><figcaption>Bulgu anı (eski çekim)</figcaption><img id="eski" alt="Bulgunun bulunduğu eski çekim"></figure>
<figure><figcaption>Şimdi (doğrulama çekimi) · kırmızı çizgi = ekran kenarı</figcaption><img id="resim" alt="Sayfanın şimdiki hali"></figure>
</div></div>
<div class="panel"><dl id="bilgi"></dl>
<div class="butonlar">
<button data-e="gercek"><kbd>1</kbd> Gerçek hata</button>
<button data-e="yanlis"><kbd>2</kbd> Yanlış alarm</button>
<button data-e="emin_degil"><kbd>3</kbd> Emin değilim</button></div>
<div class="gezinme"><button id="geri">← Önceki</button><button id="ileri">Sonraki →</button></div>
<p style="color:var(--soluk);font-size:12px">Etiketler bu tarayıcıda saklanır. Bitince "CSV indir".</p>
</div></main>
<script>
const OGELER = __OGELER__;
const ANAHTAR = "etiket_" + __IMZA__;
let etiket = {}; try { etiket = JSON.parse(localStorage.getItem(ANAHTAR) || "{}"); } catch (e) {}
let i = OGELER.findIndex(o => !etiket[o.id]); if (i < 0) i = 0;
const $ = s => document.querySelector(s);
const kacis = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function kaydet(){ try { localStorage.setItem(ANAHTAR, JSON.stringify(etiket)); } catch (e) {} }
function goster(){
  const o = OGELER[i];
  $("#resim").src = o.kesit || "";
  $("#eski").src = o.kesit_eski || "";
  $("#eskiKutu").style.display = o.kesit_eski ? "" : "none";
  $("#bilgi").innerHTML =
    `<dt>Bulgu ${i+1} / ${OGELER.length}</dt><dd><span class="rozet">${kacis(o.secim)}</span></dd>` +
    `<dt>Tür</dt><dd><b>${kacis(o.tur_adi)}</b> · ${kacis(o.cihaz)}</dd>` +
    `<dt>Kaynak / otomatik karar</dt><dd>${kacis(o.kaynak)} · ${kacis(o.otomatik_karar)}</dd>` +
    (o.eski_kanit ? `<dt>Bulgunun kanıtı</dt><dd>${kacis(o.eski_kanit)}</dd>` : "") +
    (o.ayrinti ? `<dt>Doğrulama ayrıntısı</dt><dd>${kacis(o.ayrinti)}</dd>` : "") +
    `<dt>Sayfa</dt><dd><a href="${kacis(o.url)}" target="_blank" rel="noopener">${kacis(o.url)}</a></dd>`;
  document.querySelectorAll("button[data-e]").forEach(b =>
    b.classList.toggle("secili", etiket[o.id] === b.dataset.e));
  const n = OGELER.filter(x => etiket[x.id]).length;
  $("#sayac").textContent = `${n} / ${OGELER.length} etiketlendi`;
  $("#cubuk").style.width = (100 * n / OGELER.length) + "%";
}
function sec(e){ etiket[OGELER[i].id] = e; kaydet(); if (i < OGELER.length - 1) i++; goster(); }
document.querySelectorAll("button[data-e]").forEach(b => b.onclick = () => sec(b.dataset.e));
$("#geri").onclick = () => { if (i > 0) i--; goster(); };
$("#ileri").onclick = () => { if (i < OGELER.length - 1) i++; goster(); };
document.addEventListener("keydown", ev => {
  if (ev.key === "1") sec("gercek"); else if (ev.key === "2") sec("yanlis");
  else if (ev.key === "3") sec("emin_degil");
  else if (ev.key === "ArrowLeft") $("#geri").click(); else if (ev.key === "ArrowRight") $("#ileri").click();
});
$("#indir").onclick = () => {
  const satir = ["id;etiket", ...OGELER.filter(o => etiket[o.id]).map(o => `${o.id};${etiket[o.id]}`)];
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["\\ufeff" + satir.join("\\n")], {type: "text/csv"}));
  a.download = "etiketler.csv"; a.click();
};
goster();
</script></body></html>
"""


def olustur(a):
    sonuc = csv_oku(a.sonuc)
    if not sonuc:
        sys.exit(f"[HATA] {a.sonuc} yok. Önce dogrulama.py karsilastir çalıştırın.")
    cikti = Path(a.cikti)
    (cikti / "kesitler").mkdir(parents=True, exist_ok=True)

    elle = [dict(s, secim="ELLE: kodla ölçülemedi") for s in sonuc if s["karar"] == "ELLE"]
    # Ölçümün 'hata yok' dediği bulgular: yanlış alarm kararı da gözle doğrulanmalı
    gorulmedi = [dict(s, secim="GÖRÜLMEDİ: yanlış alarm mı?") for s in sonuc
                 if s["karar"] == "GORULMEDI" and s["kaynak"] != "http"]
    dogrulanan = [s for s in sonuc if s["karar"] == "DOGRULANDI" and s["kaynak"] != "http"]
    rastgele = random.Random(a.tohum)
    ornek = rastgele.sample(dogrulanan, min(a.ornek, len(dogrulanan)))
    ornek = [dict(s, secim="ÖRNEK: otomatik doğrulamanın isabeti") for s in ornek]

    ogeler, gorulen = [], set()
    for s in elle + gorulmedi + ornek:
        s["id"] = oge_id(s)
        if s["id"] in gorulen:
            continue
        gorulen.add(s["id"])
        hedef = cikti / "kesitler" / f"{s['id']}.jpg"
        s["kesit"] = f"kesitler/{hedef.name}" if (hedef.exists() or kesit_yeni(s, a, hedef)) else ""
        eski = cikti / "kesitler" / f"{s['id']}_eski.jpg"
        s["kesit_eski"] = f"kesitler/{eski.name}" if (eski.exists() or kesit_eski(s, a, eski)) else ""
        s["otomatik_karar"] = s["karar"]
        ogeler.append(s)

    csv_yaz(cikti / "ogeler.csv", ogeler, ALANLAR)
    js = [{**{k: o.get(k, "") for k in ALANLAR}, "tur_adi": TUR_ADI.get(o["tur"], o["tur"])}
          for o in ogeler]
    veri = json.dumps(js, ensure_ascii=False).replace("</", "<\\/")
    imza = json.dumps(hashlib.md5(veri.encode()).hexdigest()[:8])
    (cikti / "etiketle.html").write_text(
        SAYFA.replace("__OGELER__", veri).replace("__IMZA__", imza), encoding="utf-8")
    eksik = sum(1 for o in ogeler if not o["kesit"])
    print(f"✅ {len(ogeler)} bulgu ({len(elle)} ELLE + {len(gorulmedi)} GÖRÜLMEDİ + "
          f"{len(ornek)} örnek) -> "
          f"{cikti / 'etiketle.html'}")
    if eksik:
        print(f"⚠️  {eksik} bulgunun görüntüsü bulunamadı (sayfa bağlantısından bakılabilir)")
    print(f"\nAçmak için: start {cikti}\\etiketle.html")


def ozet(a):
    cikti = Path(a.cikti)
    ogeler = {o["id"]: o for o in csv_oku(cikti / "ogeler.csv")}
    if not ogeler:
        sys.exit(f"[HATA] {cikti / 'ogeler.csv'} yok. Önce 'olustur' çalıştırın.")
    etiket = {r["id"]: r["etiket"] for r in csv_oku(a.etiketler) if r.get("id")}
    if not etiket:
        sys.exit(f"[HATA] {a.etiketler} boş ya da okunamadı.")

    grup = defaultdict(Counter)
    for oid, o in ogeler.items():
        if oid in etiket:
            grup[(o["secim"].split(":")[0], o["kaynak"], o["tur"])][etiket[oid]] += 1

    L = ["=" * 72, "ELLE ETİKETLEME SONUCU", "=" * 72, "",
         f"Etiketlenen: {len(etiket)} / {len(ogeler)}", "",
         f"{'grup':6s} {'kaynak':10s} {'tür':22s} {'gerçek':>6s} {'yanlış':>6s} {'emin d.':>7s} {'isabet':>7s}"]
    for (secim, kaynak, tur), c in sorted(grup.items()):
        karar_verilen = c["gercek"] + c["yanlis"]
        isabet = f"{c['gercek'] / karar_verilen:.0%}" if karar_verilen else "-"
        L.append(f"{secim:6s} {kaynak:10s} {tur[:22]:22s} {c['gercek']:6d} {c['yanlis']:6d} "
                 f"{c['emin_degil']:7d} {isabet:>7s}")
    ornek = Counter()
    for c in (v for k, v in grup.items() if k[0] == "ÖRNEK"):
        ornek.update(c)
    if ornek["gercek"] + ornek["yanlis"]:
        L += ["", f"Otomatik doğrulamanın isabeti (örneklem): "
                  f"{ornek['gercek']}/{ornek['gercek'] + ornek['yanlis']} = "
                  f"{ornek['gercek'] / (ornek['gercek'] + ornek['yanlis']):.0%}"]
    L += ["", "İsabet = gerçek / (gerçek + yanlış); 'emin değilim' hesaba katılmaz.",
          "GÖRÜLMEDİ grubunda 'gerçek' = ölçümün kaçırdığı hata, 'yanlış' = doğru ayıklanmış "
          "yanlış alarm."]
    metin = "\n".join(L)
    (cikti / "etiket_ozet.txt").write_text(metin, encoding="utf-8")

    # dogrulama sonucuna insan etiketi sütunu ekle
    sonuc = csv_oku(a.sonuc)
    for s in sonuc:
        s["insan_etiketi"] = ETIKETLER.get(etiket.get(oge_id(s), ""), "")
    alanlar = list(sonuc[0].keys()) if sonuc else ["insan_etiketi"]
    csv_yaz(cikti / "sonuc_etiketli.csv", sonuc, alanlar)
    print(metin)
    print(f"\n💾 {cikti / 'etiket_ozet.txt'}, sonuc_etiketli.csv")


def main():
    p = argparse.ArgumentParser(description="Bulguları elle etiketle (yanlış alarm ayıklama)")
    alt = p.add_subparsers(dest="komut", required=True)
    o = alt.add_parser("olustur", help="Etiketleme sayfasını üret")
    o.add_argument("--dogrulama", default="../dogrulama", help="tester --out-dir klasörü")
    o.add_argument("--klasor", nargs="+", default=["../yeniden_cekim/screenshots"],
                   help="Bulgunun bulunduğu eski çekim klasör(ler)i; sırayla aranır")
    o.add_argument("--ornek", type=int, default=30, help="DOGRULANDI'dan rastgele örnek sayısı")
    o.add_argument("--tohum", type=int, default=42)
    z = alt.add_parser("ozet", help="İndirilen etiketleri işle")
    z.add_argument("--etiketler", required=True, help="Sayfadan indirilen etiketler.csv")
    for s in (o, z):
        s.add_argument("--sonuc", default="dogrulama_cikti/sonuc.csv")
        s.add_argument("--cikti", default="etiket")
    a = p.parse_args()
    olustur(a) if a.komut == "olustur" else ozet(a)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
