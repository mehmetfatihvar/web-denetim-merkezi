"""Kırık bağlantı ve belge denetimi için okunabilir raporlar.

Tester bu iki denetimin sonucunu yalnızca CSV olarak yazar (broken_links.csv,
documents_audit.csv). Bu dosyalar virgüllü ve BOM'suz UTF-8'dir; Türkçe Windows'ta Excel
onları tek sütunda ve bozuk karakterlerle açar, belge listesinde de binlerce erişilebilir
belgenin arasında kırıklar kaybolur. Burada her biri için:
  * süzülebilir, aranabilir bir HTML raporu (kırık_link_raporu.html, belge_raporu.html)
  * Excel'de doğrudan doğru açılan bir CSV (BOM'lu, ';' ayraçlı: *_excel.csv)
üretilir. Yalnızca standart kütüphane kullanılır.
"""

import csv
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from .ayarlar import Klasorler


# ------------------------------------------------------------------ okuma
def _oku(yol: Path) -> List[dict]:
    """CSV'yi okur; aynı URL birden çok kez yazıldıysa (adım yeniden çalıştırıldığında tester
    dosyaya ekler) sonuncusu geçerlidir."""
    try:
        with open(yol, encoding="utf-8-sig", newline="") as f:
            satirlar = list(csv.DictReader(f))
    except OSError:
        return []
    tekil: Dict[str, dict] = {}
    for s in satirlar:
        if s.get("url"):
            tekil[s["url"]] = s
    return list(tekil.values())


def _alan(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def link_turu(durum: str) -> str:
    """HTTP durumu ya da hata metninden anlaşılır sınıf."""
    d = (durum or "").strip()
    if d.isdigit():
        k = int(d)
        if k == 404:
            return "404 Bulunamadı"
        if k == 410:
            return "410 Kaldırılmış"
        if k == 403:
            return "403 Erişim yasak"
        if k == 401:
            return "401 Giriş gerekli"
        if k >= 500:
            return "Sunucu hatası (5xx)"
        return f"Diğer HTTP hatası ({k})"
    a = d.lower()
    if "enotfound" in a or "getaddrinfo" in a or "name not resolved" in a:
        return "Alan adı bulunamadı (DNS)"
    if "timeout" in a or "timed out" in a:
        return "Zaman aşımı"
    if "cert" in a or "ssl" in a or "tls" in a:
        return "Sertifika (SSL) hatası"
    if "econnrefused" in a or "econnreset" in a or "refused" in a or "reset" in a:
        return "Bağlantı reddedildi/koptu"
    return "Bağlantı hatası"


BELGE_TURU = [   # (flag başlangıcı, gösterilen ad, sorunlu mu)
    ("SIZDIRILMIS", "Sızdırılmış yerel dosya yolu", True),
    ("KIRIK", "Kırık / erişilemiyor", True),
    ("ULASILAMADI", "Ulaşılamadı (bağlantı hatası)", True),
    ("erisilebilir", "Erişilebilir", False),
]


def belge_turu(flag: str):
    for bas, ad, sorunlu in BELGE_TURU:
        if (flag or "").startswith(bas):
            return ad, sorunlu
    return (flag or "Bilinmiyor"), False


# ------------------------------------------------------------------ yazma
def _excel_csv(yol: Path, basliklar: List[str], satirlar: List[List]):
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(basliklar)
        w.writerows(satirlar)


_CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--kenar:#e1e4e8;--metin:#1b1f24;--soluk:#5b6475;--vurgu:#005fb8;
--hata:#cf222e;--uyari:#9a6700;--iyi:#1a7f37}
@media (prefers-color-scheme:dark){:root{--bg:#16181d;--kart:#1f2228;--kenar:#30343c;--metin:#e8eaed;
--soluk:#a0a7b4;--vurgu:#57c8ff;--hata:#ff7b72;--uyari:#e3b341;--iyi:#56d364}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 "Segoe UI",system-ui,sans-serif;background:var(--bg);
color:var(--metin)}main{max-width:1400px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px}.soluk{color:var(--soluk)}
.kutular{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}.kutu{background:var(--kart);
border:1px solid var(--kenar);border-radius:8px;padding:12px 16px;min-width:150px}
.kutu b{display:block;font-size:24px}.kutu.hata b{color:var(--hata)}.kutu.uyari b{color:var(--uyari)}
.kutu.iyi b{color:var(--iyi)}
.cubuk{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.cip{border:1px solid var(--kenar);background:var(--kart);color:var(--metin);border-radius:16px;
padding:4px 12px;cursor:pointer;font:inherit}.cip.etkin{background:var(--vurgu);border-color:var(--vurgu);
color:#fff}input[type=search]{flex:1;min-width:240px;padding:7px 10px;border:1px solid var(--kenar);
border-radius:6px;background:var(--kart);color:var(--metin);font:inherit}
table{width:100%;border-collapse:collapse;background:var(--kart);border:1px solid var(--kenar)}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--kenar);vertical-align:top}
th{position:sticky;top:0;background:var(--kart);font-weight:600;color:var(--soluk);cursor:pointer}
td.url{word-break:break-all;min-width:280px;max-width:520px}td.durum{max-width:240px;word-break:break-word}
a{color:var(--vurgu)}.alan th:last-child{text-align:right}.kap{overflow-x:auto}
.etiket{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;white-space:nowrap;
border:1px solid currentColor}.e-hata{color:var(--hata)}.e-uyari{color:var(--uyari)}.e-iyi{color:var(--iyi)}
.sayac{margin:8px 0;color:var(--soluk)}.alan td:last-child{text-align:right}
"""

_JS = """
var filtre={tur:'%(varsayilan)s',yer:'hepsi',teyit:'hepsi'},q='';
function uyar(r,k,v){if(v==='hepsi')return true;if(k==='tur'&&v==='sorunlu')return r.dataset.sorunlu==='1';
 return r.dataset[k]===v;}
function uygula(){var n=0,s=document.querySelectorAll('#tablo tbody tr');
 for(var i=0;i<s.length;i++){var r=s[i],ok=!q||r.textContent.toLowerCase().indexOf(q)>=0;
  for(var k in filtre){if(!uyar(r,k,filtre[k]))ok=false;}
  r.style.display=ok?'':'none';if(ok)n++;}
 document.getElementById('sayac').textContent=n+' satır gösteriliyor';}
document.querySelectorAll('.cip').forEach(function(c){c.onclick=function(){
 var g=c.dataset.grup;document.querySelectorAll('.cip[data-grup="'+g+'"]').forEach(function(x){
 x.classList.remove('etkin')});c.classList.add('etkin');filtre[g]=c.dataset.deger;uygula();}});
document.getElementById('ara').oninput=function(e){q=e.target.value.toLowerCase();uygula();};
document.querySelectorAll('th').forEach(function(th,k){th.onclick=function(){
 var tb=th.closest('table').tBodies[0],rs=[].slice.call(tb.rows),yon=th.dataset.yon==='1'?-1:1;
 th.dataset.yon=yon===1?'1':'0';rs.sort(function(a,b){return a.cells[k].textContent.localeCompare(
 b.cells[k].textContent,'tr',{numeric:true})*yon});rs.forEach(function(r){tb.appendChild(r)});};});
uygula();
"""


def _e(x) -> str:
    return html.escape(str(x or ""))


def _baglanti(url: str, kisa: int = 0) -> str:
    if not url:
        return ""
    metin = url if not kisa or len(url) <= kisa else url[:kisa] + "…"
    if url.lower().startswith(("http://", "https://")):
        return f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(metin)}</a>'
    return _e(metin)


def _sayfa(baslik: str, alt: str, govde: str, varsayilan: str) -> str:
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{_e(baslik)}</title><style>{_CSS}</style></head><body><main>'
            f'<h1>{_e(baslik)}</h1><div class="soluk">{alt}</div>{govde}'
            f'<script>{_JS % {"varsayilan": varsayilan}}</script></main></body></html>')


def _cipler(grup: str, secenekler, etkin: str) -> str:
    return "".join(f'<button class="cip{" etkin" if deger == etkin else ""}" data-grup="{grup}" '
                   f'data-deger="{_e(deger)}">{_e(ad)}</button>' for deger, ad in secenekler)


TIKLAMA = {   # verify_clicks kararı -> (gösterilen, sınıf, süzgeç değeri)
    "KIRIGA GÖTÜRÜYOR": ("Tıklayınca kırığa gidiyor", "e-hata", "kirik"),
    "ÇALIŞAN YERE GİDİYOR": ("Tıklayınca çalışan yere gidiyor (yanlış alarm)", "e-iyi", "alarm"),
    "LİNK/BUTON YOK": ("Sayfada tıklanır öğe yok", "e-uyari", "belirsiz"),
    "REFERRER AÇILMADI": ("Link veren sayfa açılmadı", "e-uyari", "belirsiz"),
}


def _teyitler(rota_csv: Optional[Path], tiklama_csv: Optional[Path]) -> Dict[str, dict]:
    """url -> {'tiklama': karar, 'rota': karar}. Doğrulama adımlarının CSV'lerinden."""
    t: Dict[str, dict] = {}
    for r in (_oku_ham(tiklama_csv) if tiklama_csv else []):
        if r.get("kirik_url"):
            t.setdefault(r["kirik_url"], {})["tiklama"] = (r.get("verdict") or "").strip()
    for r in (_oku_ham(rota_csv) if rota_csv else []):
        if r.get("url"):
            t.setdefault(r["url"], {})["rota"] = (r.get("verdict") or "").strip()
    return t


def _oku_ham(yol: Path) -> List[dict]:
    try:
        with open(yol, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _teyit_hucre(t: dict):
    """(html, süzgeç değeri, düz metin)"""
    parcalar, deger, duz = [], "yok", []
    k = t.get("tiklama")
    if k:
        ad, sinif, deger = TIKLAMA.get(k, (k, "e-uyari", "belirsiz"))
        parcalar.append(f'<span class="etiket {sinif}">{_e(ad)}</span>')
        duz.append(ad)
    r = t.get("rota")
    if r:
        if r.startswith("GERÇEKTEN KIRIK"):
            ad, sinif = "Doğrudan açınca kırık", "e-hata"
            deger = deger if deger != "yok" else "kirik"
        elif r.startswith(("İÇERİK GELİYOR", "ÇALIŞIYOR")):
            ad, sinif = "Doğrudan açınca içerik geliyor", "e-iyi"
            deger = deger if deger != "yok" else "alarm"
        else:
            ad, sinif = r, "e-uyari"
        parcalar.append(f'<div><span class="etiket {sinif}">{_e(ad)}</span></div>')
        duz.append(ad)
    if not parcalar:
        return '<span class="soluk">teyit edilmedi</span>', "yok", ""
    return "".join(parcalar), deger, " / ".join(duz)


def link_raporu(csv_yolu: Path, html_yolu: Path, site_url: str = "", site_adi: str = "",
                rota_csv: Optional[Path] = None, tiklama_csv: Optional[Path] = None) -> dict:
    """broken_links.csv -> HTML + Excel CSV. Doğrulama adımlarının (doğrudan erişim, buton
    tıklama) kararları varsa site içi kırık bağlantıların yanında gösterilir."""
    kayitlar = _oku(csv_yolu)
    teyit = _teyitler(rota_csv, tiklama_csv)
    site = _alan(site_url)
    satirlar = []
    for r in kayitlar:
        tur = link_turu(r.get("status", ""))
        alan = _alan(r["url"])
        yer = "ic" if site and (alan == site or alan.endswith("." + site)) else "dis"
        satirlar.append((r, tur, alan, yer, _teyit_hucre(teyit.get(r["url"], {}))))
    turler = Counter(t for _, t, _, _, _ in satirlar)
    alanlar = Counter(a for _, _, a, _, _ in satirlar)
    ic = sum(1 for _, _, _, y, _ in satirlar if y == "ic")
    teyit_say = Counter(h[1] for *_, h in satirlar)

    kutular = (f'<div class="kutular"><div class="kutu hata"><b>{len(satirlar):,}</b>kırık bağlantı</div>'
               f'<div class="kutu"><b>{ic:,}</b>site içi</div>'
               f'<div class="kutu"><b>{len(satirlar) - ic:,}</b>dış site</div>'
               f'<div class="kutu"><b>{len(alanlar):,}</b>farklı alan adı</div>' +
               (f'<div class="kutu hata"><b>{teyit_say["kirik"]:,}</b>tıklama/erişimle kırık teyitli</div>'
                f'<div class="kutu iyi"><b>{teyit_say["alarm"]:,}</b>yanlış alarm (aslında açılıyor)</div>'
                if teyit else "") + '</div>').replace(",", ".")
    alan_tablo = "".join(f"<tr><td>{_e(a or '(adres çözülemedi)')}</td><td>{n}</td></tr>"
                         for a, n in alanlar.most_common(15))
    tur_cip = [("hepsi", f"Tümü ({len(satirlar)})")] + [(t, f"{t} ({n})") for t, n in turler.most_common()]
    yer_cip = [("hepsi", "İç + dış"), ("ic", f"Site içi ({ic})"), ("dis", f"Dış ({len(satirlar) - ic})")]
    teyit_cip = [("hepsi", "Teyit: hepsi"), ("kirik", f"Kırık teyitli ({teyit_say['kirik']})"),
                 ("alarm", f"Yanlış alarm ({teyit_say['alarm']})"),
                 ("belirsiz", f"Belirsiz ({teyit_say['belirsiz']})"),
                 ("yok", f"Teyit edilmedi ({teyit_say['yok']})")]
    govde_satir = "".join(
        f'<tr data-tur="{_e(t)}" data-yer="{y}" data-teyit="{h[1]}" data-sorunlu="1">'
        f'<td class="url">{_baglanti(r["url"])}</td>'
        f'<td class="durum"><span class="etiket e-hata">{_e(t)}</span><div class="soluk">{_e(r.get("status", ""))[:120]}'
        f'</div></td><td>{"Site içi" if y == "ic" else "Dış"}</td><td class="durum">{h[0]}</td>'
        f'<td class="url">{_baglanti(r.get("kaynak_sayfa", ""), 90)}</td><td>{_e(r.get("buton_metni", ""))}</td></tr>'
        for r, t, a, y, h in sorted(satirlar, key=lambda x: (x[3], x[4][1] != "kirik", x[1], x[0]["url"])))
    govde = (kutular +
             '<h2>En çok kırık bağlantı olan alan adları</h2><table class="alan"><thead><tr><th>Alan adı</th>'
             f'<th>Kırık</th></tr></thead><tbody>{alan_tablo}</tbody></table>'
             '<h2>Bütün kırık bağlantılar</h2>'
             f'<div class="cubuk">{_cipler("tur", tur_cip, "hepsi")}</div>'
             f'<div class="cubuk">{_cipler("yer", yer_cip, "hepsi")}</div>'
             + (f'<div class="cubuk">{_cipler("teyit", teyit_cip, "hepsi")}</div>' if teyit else "") +
             '<div class="cubuk"><input type="search" id="ara" placeholder="Adres, sayfa ya da buton metninde ara…"></div>'
             '<div class="sayac" id="sayac"></div><div class="kap"><table id="tablo"><thead><tr><th>Kırık adres</th>'
             '<th>Sorun</th><th>Yer</th><th>Teyit</th><th>Linki veren sayfa</th><th>Buton/link metni</th></tr></thead>'
             f'<tbody>{govde_satir}</tbody></table></div>')
    alt = (f'{_e(site_adi)} · Sayfalardaki bütün bağlantılar tek tek denendi; burada yalnız '
           f'açılmayanlar var. <b>Teyit</b> sütunu Doğrulama adımlarının sonucudur: site içi kırık '
           f'adres tarayıcıda doğrudan açıldı ve/veya link veren sayfada butona gerçekten tıklandı '
           f'(tıklama örneklemle yapılır, bkz. Ayarlar). Üretildi: {datetime.now():%d.%m.%Y %H:%M} · Kaynak: {_e(csv_yolu.name)}')
    html_yolu.write_text(_sayfa("Kırık bağlantı raporu", alt, govde, "hepsi"), encoding="utf-8")
    _excel_csv(html_yolu.with_name("kirik_linkler_excel.csv"),
               ["Kırık adres", "Sorun", "HTTP durumu / hata", "Yer", "Alan adı", "Teyit", "Linki veren sayfa",
                "Buton/link metni"],
               [[r["url"], t, r.get("status", ""), "Site içi" if y == "ic" else "Dış", a, h[2],
                 r.get("kaynak_sayfa", ""), r.get("buton_metni", "")] for r, t, a, y, h in satirlar])
    return {"toplam": len(satirlar), "ic": ic, "turler": dict(turler),
            "teyit_kirik": teyit_say["kirik"], "teyit_alarm": teyit_say["alarm"]}


def belge_raporu(csv_yolu: Path, html_yolu: Path, site_adi: str = "") -> dict:
    """documents_audit.csv -> HTML + Excel CSV. Varsayılan görünüm yalnız sorunlu belgeler."""
    kayitlar = _oku(csv_yolu)
    satirlar = []
    for r in kayitlar:
        tur, sorunlu = belge_turu(r.get("flag", ""))
        satirlar.append((r, tur, sorunlu))
    turler = Counter(t for _, t, _ in satirlar)
    sorunlu = sum(1 for *_, s in satirlar if s)
    sizinti = sum(1 for _, t, _ in satirlar if t == BELGE_TURU[0][1])

    kutular = (f'<div class="kutular"><div class="kutu"><b>{len(satirlar):,}</b>belge/dosya bağlantısı</div>'
               f'<div class="kutu hata"><b>{sorunlu:,}</b>sorunlu</div>'
               f'<div class="kutu uyari"><b>{sizinti:,}</b>sızdırılmış yerel yol</div>'
               f'<div class="kutu iyi"><b>{len(satirlar) - sorunlu:,}</b>erişilebilir</div></div>'
               ).replace(",", ".")
    tur_cip = ([("sorunlu", f"Yalnız sorunlular ({sorunlu})"), ("hepsi", f"Tümü ({len(satirlar)})")] +
               [(ad, f"{ad} ({turler[ad]})") for _, ad, _ in BELGE_TURU if turler.get(ad)])
    sinif = {BELGE_TURU[0][1]: "e-uyari", BELGE_TURU[1][1]: "e-hata", BELGE_TURU[2][1]: "e-hata"}
    govde_satir = "".join(
        f'<tr data-tur="{_e(t)}" data-yer="hepsi" data-sorunlu="{1 if s else 0}">'
        f'<td class="url">{_baglanti(r["url"])}</td>'
        f'<td class="durum"><span class="etiket {sinif.get(t, "e-iyi")}">{_e(t)}</span>'
        f'<div class="soluk">{_e(r.get("status", ""))[:120]}</div></td>'
        f'<td>{_e(r.get("content_type", "").split(";")[0])}</td><td>{_e(r.get("size", ""))}</td>'
        f'<td class="url">{_baglanti(r.get("kaynak_sayfa", ""), 90)}</td><td>{_e(r.get("buton_metni", ""))}</td></tr>'
        for r, t, s in sorted(satirlar, key=lambda x: (not x[2], x[1], x[0]["url"])))
    govde = (kutular +
             '<p class="soluk">Sızdırılmış yerel yol: editörün bilgisayarındaki dosya yolu (ör. '
             '<code>file:///C:/Users/…</code>) sayfaya yapıştırılmış; ziyaretçide açılmaz ve iç '
             'kullanıcı/klasör adlarını açığa çıkarır.</p>'
             f'<div class="cubuk">{_cipler("tur", tur_cip, "sorunlu")}</div>'
             '<div class="cubuk"><input type="search" id="ara" placeholder="Adres, sayfa ya da metinde ara…">'
             '</div><div class="sayac" id="sayac"></div><table id="tablo"><thead><tr><th>Belge adresi</th>'
             '<th>Durum</th><th>Tür</th><th>Boyut</th><th>Linki veren sayfa</th><th>Link metni</th></tr>'
             f'</thead><tbody>{govde_satir}</tbody></table></div>')
    alt = (f'{_e(site_adi)} · Sayfalardaki PDF, Word, Excel vb. bağlantıları denendi. '
           f'Üretildi: {datetime.now():%d.%m.%Y %H:%M} · Kaynak: {_e(csv_yolu.name)}')
    html_yolu.write_text(_sayfa("Belge denetimi raporu", alt, govde, "sorunlu"), encoding="utf-8")
    _excel_csv(html_yolu.with_name("belge_denetimi_excel.csv"),
               ["Belge adresi", "Durum", "Sorunlu", "HTTP durumu / hata", "Tür", "Boyut",
                "Linki veren sayfa", "Link metni"],
               [[r["url"], t, "evet" if s else "hayır", r.get("status", ""),
                 r.get("content_type", ""), r.get("size", ""), r.get("kaynak_sayfa", ""),
                 r.get("buton_metni", "")] for r, t, s in satirlar])
    return {"toplam": len(satirlar), "sorunlu": sorunlu, "sizinti": sizinti, "turler": dict(turler)}


# ------------------------------------------------------------------ programdan kullanım
def _guncel(csv_yolu: Path, html_yolu: Path, uret, *ekler: Path) -> Optional[Path]:
    """CSV varsa ve HTML yoksa ya da CSV'den (veya eklerden) eskiyse raporu üretir."""
    if not csv_yolu.exists():
        return None
    kaynak = max([csv_yolu.stat().st_mtime] + [e.stat().st_mtime for e in ekler if e.exists()])
    if not html_yolu.exists() or html_yolu.stat().st_mtime < kaynak:
        uret()
    return html_yolu


def _link_uret(ayar: dict):
    k = Klasorler(ayar)
    c, h = k.link / "broken_links.csv", k.link / "kirik_link_raporu.html"
    return c, h, lambda: link_raporu(c, h, ayar.get("site_url", ""), ayar.get("site_adi", ""),
                                     k.rota_csv, k.tiklama_csv)


def link_raporu_yolu(ayar: dict) -> Path:
    k = Klasorler(ayar)
    c, h, uret = _link_uret(ayar)
    return _guncel(c, h, uret, k.rota_csv, k.tiklama_csv) or h


def belge_raporu_yolu(ayar: dict) -> Path:
    k = Klasorler(ayar)
    c, h = k.belge / "documents_audit.csv", k.belge / "belge_raporu.html"
    return _guncel(c, h, lambda: belge_raporu(c, h, ayar.get("site_adi", ""))) or h


def adim_komutu(tur: str, ayar: dict):
    """Belge/link adımının sonuna eklenen rapor üretimi (Komut fonksiyonu)."""
    def calis(yaz):
        k = Klasorler(ayar)
        if tur == "link":
            c, h, uret = _link_uret(ayar)
            if not c.exists():
                yaz("Kırık bağlantı bulunmadı ya da denetim tamamlanmadı; rapor üretilmedi.\n")
                return 0
            o = uret()
            teyit = (f"; teyit: {o['teyit_kirik']} kırık, {o['teyit_alarm']} yanlış alarm"
                     if o["teyit_kirik"] or o["teyit_alarm"] else "")
            yaz(f"Kırık bağlantı raporu: {o['toplam']} kırık ({o['ic']} site içi{teyit}) -> {h}\n")
        else:
            c, h = k.belge / "documents_audit.csv", k.belge / "belge_raporu.html"
            if not c.exists():
                yaz("Belge listesi yok; rapor üretilmedi.\n")
                return 0
            o = belge_raporu(c, h, ayar.get("site_adi", ""))
            yaz(f"Belge raporu: {o['toplam']} belge, {o['sorunlu']} sorunlu "
                f"({o['sizinti']} sızdırılmış yerel yol) -> {h}\n")
        return 0
    return calis


if __name__ == "__main__":     # elle: python -m merkez.denetim_raporu link|belge CSV [HTML]
    import sys
    tur, kaynak = sys.argv[1], Path(sys.argv[2])
    hedef = Path(sys.argv[3]) if len(sys.argv) > 3 else kaynak.with_suffix(".html")
    print(json.dumps((link_raporu if tur == "link" else belge_raporu)(kaynak, hedef), ensure_ascii=False))
