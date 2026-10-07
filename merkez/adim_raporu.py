"""Her adım bittiğinde o adımın ne yaptığını gösteren HTML rapor (adım raporu).

Bazı adımların kendine özgü raporu vardır (test raporu, görsel kusur raporu ...), bazıları
yalnız CSV/TXT/JSON üretir, bazıları (kurulum, ortam kontrolü, Bologna) hiç dosya üretmez ve
sonucu yalnız çalışma kaydında kalır. Burada çalıştırıcı, hangi adım olursa olsun, adım
bitince tek biçimde bir sayfa yazar:
  * sonuç, süre, hata/uyarı sayısı, çalıştırılan komutlar
  * hatalar ve uyarılar listesi
  * adımın ürettiği her dosya: HTML raporlara bağlantı, CSV'ler aranabilir tablo, TXT'ler
    metin, JSON'lar özet (öğe sayıları), diğerleri boyutuyla bağlantı
  * çalışma kaydının sonu (tamamı bağlantıyla)
Raporlar <çıktı kökü>/adim_raporlari/ altına yazılır; index.html hepsini en yeniden eskiye
listeler. Yalnızca standart kütüphane kullanılır.
"""

import csv
import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

ONIZLEME_SATIR = 500           # CSV önizlemesinde en fazla satır
METIN_SINIRI = 200_000         # TXT önizlemesinde en fazla karakter
KAYIT_SATIR = 400              # çalışma kaydının gösterilen son satırları

DURUM = {"basarili": ("Başarılı", "iyi"), "hatali": ("Başarısız", "hata"), "durdu": ("Durduruldu", "uyari")}

_CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--kenar:#e1e4e8;--metin:#1b1f24;--soluk:#5b6475;--vurgu:#005fb8;
--hata:#cf222e;--uyari:#9a6700;--iyi:#1a7f37;--konsol:#0f1419;--konsol-metin:#d6dde6}
@media (prefers-color-scheme:dark){:root{--bg:#16181d;--kart:#1f2228;--kenar:#30343c;--metin:#e8eaed;
--soluk:#a0a7b4;--vurgu:#57c8ff;--hata:#ff7b72;--uyari:#e3b341;--iyi:#56d364}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 "Segoe UI",system-ui,sans-serif;background:var(--bg);
color:var(--metin)}main{max-width:1400px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:30px 0 10px}h3{font-size:15px;margin:22px 0 6px}
.soluk{color:var(--soluk)}a{color:var(--vurgu)}
.kutular{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.kutu{background:var(--kart);
border:1px solid var(--kenar);border-radius:8px;padding:10px 16px;min-width:140px}.kutu b{display:block;font-size:20px}
.iyi b,.iyi{color:var(--iyi)}.hata b,.hata{color:var(--hata)}.uyari b,.uyari{color:var(--uyari)}
.kart{background:var(--kart);border:1px solid var(--kenar);border-radius:8px;padding:14px 16px;margin:10px 0}
table{width:100%;border-collapse:collapse;background:var(--kart);border:1px solid var(--kenar);font-size:13px}
th,td{text-align:left;padding:6px 9px;border-bottom:1px solid var(--kenar);vertical-align:top;word-break:break-word}
th{background:var(--kart);color:var(--soluk);font-weight:600;position:sticky;top:0}
.kap{overflow:auto;max-height:560px}pre{background:var(--konsol);color:var(--konsol-metin);padding:12px;
border-radius:6px;overflow:auto;max-height:560px;font:12px/1.4 Consolas,"Cascadia Mono",monospace;white-space:pre-wrap}
code{font:12px Consolas,monospace}input[type=search]{width:100%;max-width:520px;padding:6px 10px;margin:6px 0;
border:1px solid var(--kenar);border-radius:6px;background:var(--kart);color:var(--metin)}
.dosya{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
td.dar{white-space:nowrap}
"""
_JS = """
document.querySelectorAll('input[data-tablo]').forEach(function(g){g.oninput=function(){
 var q=g.value.toLowerCase(),t=document.getElementById(g.dataset.tablo);
 [].forEach.call(t.tBodies[0].rows,function(r){r.style.display=!q||r.textContent.toLowerCase().indexOf(q)>=0?'':'none'})}});
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _boyut(n: int) -> str:
    for birim in ("B", "KB", "MB", "GB"):
        if n < 1024 or birim == "GB":
            return f"{n:.0f} {birim}" if birim == "B" else f"{n:.1f} {birim}"
        n /= 1024


def _bag(hedef: Path, kaynak_klasor: Path) -> str:
    """Rapordan dosyaya göreli bağlantı (klasör taşınsa da çalışır); olmazsa file:// adresi."""
    try:
        return Path(os.path.relpath(hedef, kaynak_klasor)).as_posix()
    except ValueError:              # Windows'ta farklı sürücü
        return hedef.resolve().as_uri()


def _csv_onizleme(yol: Path, kimlik: str) -> str:
    try:
        with open(yol, encoding="utf-8-sig", newline="", errors="replace") as f:
            ilk = f.readline()
            f.seek(0)
            ayrac = ";" if ilk.count(";") > ilk.count(",") else ","
            okuyucu = csv.reader(f, delimiter=ayrac)
            baslik = next(okuyucu, [])
            satirlar, toplam = [], 0
            for s in okuyucu:
                toplam += 1
                if len(satirlar) < ONIZLEME_SATIR:
                    satirlar.append(s)
    except OSError as e:
        return f'<p class="hata">Okunamadı: {_e(e)}</p>'
    not_ = (f"{toplam} satır" + (f"; ilk {ONIZLEME_SATIR} satır gösteriliyor (tamamı dosyada)"
                                  if toplam > ONIZLEME_SATIR else ""))
    govde = "".join("<tr>" + "".join(f"<td>{_e(h[:400])}</td>" for h in s) + "</tr>" for s in satirlar)
    return (f'<div class="soluk">{not_}</div>'
            f'<input type="search" data-tablo="{kimlik}" placeholder="Bu tabloda ara…">'
            f'<div class="kap"><table id="{kimlik}"><thead><tr>'
            + "".join(f"<th>{_e(b)}</th>" for b in baslik) +
            f"</tr></thead><tbody>{govde}</tbody></table></div>")


def _json_ozet(yol: Path) -> str:
    try:
        if yol.stat().st_size > 300_000_000:
            return '<p class="soluk">Dosya çok büyük; özet çıkarılmadı.</p>'
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f'<p class="hata">Okunamadı: {_e(e)}</p>'

    def tanim(v):
        if isinstance(v, list):
            return f"liste, {len(v):,} öğe".replace(",", ".")
        if isinstance(v, dict):
            return f"sözlük, {len(v):,} anahtar".replace(",", ".")
        metin = json.dumps(v, ensure_ascii=False)
        return metin if len(metin) <= 200 else metin[:200] + "…"
    if isinstance(veri, dict):
        satir = "".join(f"<tr><td><code>{_e(k)}</code></td><td>{_e(tanim(v))}</td></tr>" for k, v in veri.items())
        return f"<table><thead><tr><th>Alan</th><th>İçerik</th></tr></thead><tbody>{satir}</tbody></table>"
    if isinstance(veri, list):
        ornek = json.dumps(veri[:5], ensure_ascii=False, indent=1)
        sayi = f"{len(veri):,}".replace(",", ".")
        return f'<div class="soluk">{sayi} öğe; ilk 5:</div><pre>{_e(ornek[:20000])}</pre>'
    return f"<pre>{_e(tanim(veri))}</pre>"


def _metin(yol: Path) -> str:
    try:
        with open(yol, encoding="utf-8-sig", errors="replace") as f:
            m = f.read(METIN_SINIRI + 1)
    except OSError as e:
        return f'<p class="hata">Okunamadı: {_e(e)}</p>'
    kes = len(m) > METIN_SINIRI
    return f"<pre>{_e(m[:METIN_SINIRI])}</pre>" + ('<p class="soluk">… (devamı dosyada)</p>' if kes else "")


def _dosya_bolumu(yol: Path, klasor: Path, no: int) -> str:
    try:
        boyut = _boyut(yol.stat().st_size)
        zaman = datetime.fromtimestamp(yol.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
    except OSError:
        return ""
    uzanti = yol.suffix.lower()
    bas = (f'<div class="kart"><div class="dosya"><h3 style="margin:0">{_e(yol.name)}</h3>'
           f'<a href="{_e(_bag(yol, klasor))}">dosyayı aç</a>'
           f'<span class="soluk">{boyut} · {zaman} · {_e(yol.parent)}</span></div>')
    if uzanti in (".html", ".htm"):
        icerik = (f'<p>Bu adımın kendi raporu. <a href="{_e(_bag(yol, klasor))}"><b>Raporu aç →</b></a></p>')
    elif uzanti == ".csv":
        icerik = _csv_onizleme(yol, f"t{no}")
    elif uzanti in (".txt", ".log", ".css", ".md"):
        icerik = _metin(yol)
    elif uzanti == ".json":
        icerik = _json_ozet(yol)
    else:
        icerik = '<p class="soluk">Önizleme yok; dosyayı açarak bakın.</p>'
    return bas + icerik + "</div>"


def _kayit_sonu(yol: str) -> str:
    if not yol or not Path(yol).exists():
        return '<p class="soluk">Çalışma kaydı yok.</p>'
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            satirlar = f.readlines()
    except OSError as e:
        return f'<p class="hata">Okunamadı: {_e(e)}</p>'
    not_ = (f"Son {KAYIT_SATIR} satır ({len(satirlar)} satırdan)" if len(satirlar) > KAYIT_SATIR
            else f"{len(satirlar)} satır")
    return f'<div class="soluk">{not_}</div><pre>{_e("".join(satirlar[-KAYIT_SATIR:]))}</pre>'


def uret(klasor: Path, kayit: dict, komutlar: List[str], aciklama: str = "", site: str = "") -> Path:
    """Bir adımın raporunu yazar; dizini günceller. kayit: çalıştırıcının adım sonucu."""
    klasor.mkdir(parents=True, exist_ok=True)
    simdi = datetime.now()
    ad = f"{simdi:%Y%m%d_%H%M%S}_{kayit['id']}"
    durum, sinif = DURUM.get(kayit["sonuc"], (kayit["sonuc"], ""))
    sure = kayit.get("sure_sn", 0)
    sure_metni = f"{sure:.0f} sn" if sure < 60 else (f"{sure / 60:.1f} dk" if sure < 3600 else f"{sure / 3600:.1f} sa")

    kutular = (f'<div class="kutular"><div class="kutu {sinif}"><b>{durum}</b>sonuç</div>'
               f'<div class="kutu"><b>{sure_metni}</b>süre</div>'
               f'<div class="kutu {"hata" if kayit["hata"] else ""}"><b>{kayit["hata"]}</b>hata</div>'
               f'<div class="kutu {"uyari" if kayit["uyari"] else ""}"><b>{kayit["uyari"]}</b>uyarı</div>'
               f'<div class="kutu"><b>{len(kayit.get("ciktilar", []))}</b>çıktı dosyası</div></div>')
    komut = "".join(f"<pre>{_e(k)}</pre>" for k in komutlar) or '<p class="soluk">—</p>'
    sorunlar = kayit.get("sorunlar", [])
    sorun_html = ("<div class=\"kap\"><table><thead><tr><th>Saat</th><th>Tür</th><th>Satır</th></tr></thead><tbody>" +
                  "".join(f'<tr><td class="dar">{_e(s.get("zaman"))}</td><td class="dar {"hata" if s.get("seviye") == "hata" else "uyari"}">'
                          f'{"Hata" if s.get("seviye") == "hata" else "Uyarı"}</td><td><code>{_e(s.get("satir"))}</code></td></tr>'
                          for s in sorunlar) + "</tbody></table></div>") if sorunlar else \
        '<p class="soluk">Hata ya da uyarı yok.</p>'
    dosyalar = [Path(c) for c in kayit.get("ciktilar", [])]
    dosya_html = "".join(_dosya_bolumu(p, klasor, i) for i, p in enumerate(dosyalar)) or \
        '<p class="soluk">Bu adım dosya üretmez; sonucu aşağıdaki çalışma kaydındadır.</p>'
    kayit_bag = (f' · <a href="{_e(_bag(Path(kayit["kayit"]), klasor))}">tam çalışma kaydı</a>'
                 if kayit.get("kayit") else "")
    sayfa = (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{_e(kayit["ad"])} · adım raporu</title><style>{_CSS}</style></head><body><main>'
             f'<div class="soluk"><a href="index.html">← Bütün adım raporları</a></div>'
             f'<h1>{_e(kayit["ad"])}</h1><div class="soluk">{_e(site)} · bitiş {simdi:%d.%m.%Y %H:%M:%S}'
             f'{kayit_bag}</div>'
             + (f'<p>{_e(aciklama)}</p>' if aciklama else "") + kutular +
             f'<h2>Çıktılar</h2>{dosya_html}'
             f'<h2>Hatalar ve uyarılar</h2>{sorun_html}'
             f'<h2>Çalıştırılan komutlar</h2>{komut}'
             f'<h2>Çalışma kaydı</h2>{_kayit_sonu(kayit.get("kayit", ""))}'
             f'<script>{_JS}</script></main></body></html>')
    hedef = klasor / f"{ad}.html"
    hedef.write_text(sayfa, encoding="utf-8")
    meta = {"dosya": hedef.name, "id": kayit["id"], "ad": kayit["ad"], "sonuc": kayit["sonuc"],
            "sure_sn": sure, "hata": kayit["hata"], "uyari": kayit["uyari"],
            "bitis": simdi.strftime("%d.%m.%Y %H:%M:%S"), "cikti": len(dosyalar)}
    (klasor / f"{ad}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    dizin_yaz(klasor, site)
    return hedef


def dizin_yaz(klasor: Path, site: str = "") -> Path:
    metalar = []
    for j in sorted(klasor.glob("*.json"), reverse=True):
        try:
            metalar.append(json.loads(j.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    satir = "".join(
        f'<tr><td>{_e(m["bitis"])}</td><td><a href="{_e(m["dosya"])}">{_e(m["ad"])}</a></td>'
        f'<td class="{DURUM.get(m["sonuc"], ("", ""))[1]}">{_e(DURUM.get(m["sonuc"], (m["sonuc"],))[0])}</td>'
        f'<td>{m["sure_sn"]:.0f} sn</td><td>{m["hata"]} / {m["uyari"]}</td><td>{m["cikti"]}</td></tr>'
        for m in metalar)
    sayfa = (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Adım raporları</title><style>{_CSS}</style></head><body><main>'
             f'<h1>Adım raporları</h1><div class="soluk">{_e(site)} · Her adım her çalışmada bir rapor '
             f'üretir; en yeni üstte. {len(metalar)} rapor.</div>'
             f'<input type="search" data-tablo="dizin" placeholder="Adım adında ara…">'
             f'<table id="dizin"><thead><tr><th>Bitiş</th><th>Adım</th><th>Sonuç</th><th>Süre</th>'
             f'<th>Hata / uyarı</th><th>Çıktı</th></tr></thead><tbody>{satir}</tbody></table>'
             f'<script>{_JS}</script></main></body></html>')
    hedef = klasor / "index.html"
    hedef.write_text(sayfa, encoding="utf-8")
    return hedef


def son_rapor(klasor: Path, adim_id: str):
    """Bu adımın en son raporu (yoksa None). Ad biçimi: YYYYMMDD_HHMMSS_<adım>.html"""
    adaylar = sorted(p for p in klasor.glob(f"*_{adim_id}.html") if p.stem[16:] == adim_id)
    return adaylar[-1] if adaylar else None
