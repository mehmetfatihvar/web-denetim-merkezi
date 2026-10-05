#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 KANITLI EKRAN GÖRÜNTÜSÜ / TEST ARACI  (cekim/tester.py)
================================================================================
 Amaç: Phase 5'te keşfedilen TÜM tıklanabilir linkleri gerçek bir tarayıcıda
       (Chromium/Playwright) tek tek test eder ve her test için KANIT üretir:
         • Masaüstü tam sayfa ekran görüntüsü (PNG)
         • Mobil (375px) ekran görüntüsü  -> responsive kanıtı
         • (İsteğe bağlı) sayfa videosu (WEBM)
         • Konsol hataları, ağ hataları, yüklenme süresi
       Sonuçları hem makine-okur (JSON/Excel/CSV) hem de SUNULABİLİR bir
       HTML raporunda (küçük resimler + kanıt bağlantıları) toplar.

--------------------------------------------------------------------------------
 KURULUM (kendi bilgisayarında, bir kez):
     pip install playwright pandas openpyxl
     playwright install chromium

 ÇALIŞTIRMA ÖRNEKLERİ:
     # 1) Hızlı deneme — ilk 50 sayfa, masaüstü+mobil ekran görüntüsü:
     python tester.py --limit 50

     # 2) Belirli aralık (parça parça; 17k sayfayı bölerek test için):
     python tester.py --offset 0 --limit 2000
     python tester.py --offset 2000 --limit 2000   # sonraki parça

     # 3) Video kanıtı da al (yavaş + çok yer kaplar, kritik sayfalar için):
     python tester.py --limit 30 --video

     # 4) Sayfadaki linkleri de kontrol et (kırık link kanıtı):
     python tester.py --limit 100 --check-links

     # 4b) Görsel/UI kusur denetimi (HTTP'den bağımsız; işaretli kanıt görüntülü):
     python tester.py --out-dir gorsel --check-visual --no-screenshots

     # 5) Kaldığın yerden devam et (aynı klasöre tekrar çalıştır):
     python tester.py --limit 2000 --resume

 ÇIKTILAR (test_output/ klasörü altında):
     screenshots/<sayfa>__desktop.png
     screenshots/<sayfa>__mobile.png
     videos/<sayfa>.webm                (--video verilirse)
     report.html      <-- SUNUM İÇİN: kanıtlı, filtrelenebilir tablo
     results.json     <-- tüm ham veriler
     report.xlsx      <-- Excel tablosu
     summary.txt      <-- kısa özet
     broken_links.csv <-- (--check-links verilirse)

--------------------------------------------------------------------------------
 KAYNAK LİNKLER (öncelik sırası, --source ile değiştirilebilir):
     final_complete_site_map.json  (url_list: 17.411 sayfa)   <-- varsayılan
     comprehensive_test_results.json (test edilmiş url'ler)
     all_links_found.json
     site_map.json
 Bozuk/binary URL'ler otomatik ayıklanır.
================================================================================
"""

import argparse
import asyncio
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[HATA] Playwright kurulu değil. Kur:")
    print("       pip install playwright pandas openpyxl")
    print("       playwright install chromium")
    sys.exit(1)

# ------------------------------------------------------------------ sabitler ---
# Rapor başlığında gösterilen site adresi. Koda yazılmaz: DENETIM_SITE ortam
# değişkeninden okunur, yoksa link kaynağındaki ilk URL'den çıkarılır.
BASE_URL = os.environ.get("DENETIM_SITE", "")
# Siteye özgü ayarlar --site-adi / --locale / --user-agent ile verilir (Web Denetim Merkezi
# profilden geçirir). Site adı verilmezse site adresinin alan adı kullanılır.
SITE_NAME = ""
LOCALE = "tr-TR"
USER_AGENT = "Web-Denetim-Tester/3.0 (kanitli test)"
TURKISH_CHARS = "çÇğĞıİöÖşŞüÜ"
NON_HTTP_SCHEMES = ("mailto:", "tel:", "javascript:", "file:", "#", "data:", "sms:")
# Belge/dosya uzantıları (belge denetimi için)
DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".rar", ".7z", ".csv", ".txt", ".rtf", ".odt", ".ods", ".odp")
# Belge Content-Type imzaları (JS ile açılan uzantısız dosyaları yakalamak için)
DOC_CTYPES = ("application/pdf", "msword", "officedocument", "ms-excel",
              "ms-powerpoint", "application/zip", "application/x-rar",
              "application/octet-stream", "text/csv", "application/rtf")
DESKTOP_VIEWPORT = {"width": 1366, "height": 900}
TABLET_VIEWPORT = {"width": 768, "height": 1024}  # iPad benzeri
MOBILE_VIEWPORT = {"width": 375, "height": 812}   # iPhone X benzeri
OUT_DIR = "test_output"

SECURITY_HEADERS = {
    "hsts": "strict-transport-security",
    "csp": "content-security-policy",
    "x_frame_options": "x-frame-options",
    "x_content_type_options": "x-content-type-options",
    "x_xss_protection": "x-xss-protection",
    "referrer_policy": "referrer-policy",
}

# Her testin ne kontrol ettiği — HTML raporundaki "Test Koşulları" bölümü için
TEST_CONDITIONS = [
    ("HTTP Durum", "Sayfa 200 (Başarılı) dönüyor mu? 4xx/5xx = hata."),
    ("Yüklenme Süresi", "Sayfanın 'load' olayına kadar geçen süre (sn). Hedef < 3s."),
    ("Güvenlik Başlıkları", "HSTS, CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy başlıkları mevcut mu?"),
    ("Türkçe Karakter", "Sayfa render edildikten sonra ç,ğ,ı,ş,ö,ü doğru görünüyor mu? (mojibake/bozuk encoding var mı?)"),
    ("Erişilebilirlik", "Görsellerde alt metni, tek bir H1, form etiketleri, html lang özniteliği var mı? (WCAG)"),
    ("Mobil Uyum", "Viewport meta etiketi ve responsive (media query) var mı? 375px'te görünüm bozuluyor mu?"),
    ("Konsol/JS Hataları", "Sayfa yüklenirken JavaScript hatası veya başarısız ağ isteği oluşuyor mu?"),
    ("Formlar", "Sayfadaki form sayısı ve alanları."),
    ("Kanıt", "Masaüstü + mobil tam sayfa ekran görüntüsü (ve istenirse video)."),
]

# Görsel kusur türleri -> (etiket, renk, öncelik). Rapor + Excel bunu kullanır.
VISUAL_TYPES = {
    "icerik_tasmasi": ("İçerik ekrandan taşıyor (yatay kayma)", "#cf222e", "yuksek"),
    "kirik_gorsel":   ("Kırık görsel (yüklenmedi)",             "#cf222e", "yuksek"),
    "bos_sayfa":      ("Boş / çökmüş render",                   "#cf222e", "yuksek"),
    "metin_kirpma":   ("Metin kutusuna sığmıyor (kırpılma)",    "#9a6700", "orta"),
}

# ---------------------------------------------------------- şablon kümeleme ---
_LANG_SEGS = {"en", "tr", "de", "fr", "ar", "ru", "az", "fa"}


def _leaf_of(url):
    """URL'nin dil-sonrası ilk ve son (yaprak) segmentlerini döndürür (normalize)."""
    p = urlparse(url)
    segs = [s for s in (p.path or "/").split("/") if s]
    if segs and segs[0].lower() in _LANG_SEGS:
        segs = segs[1:]

    def norm(s):
        s = s.lower()
        if re.search(r"\d", s) or re.fullmatch(r"[0-9a-f]{8,}", s):
            return "*"
        return s
    if not segs:
        return ("", "", 0)
    return (norm(segs[0]), norm(segs[-1]), len(segs))


def template_signature(url, leaf_vocab=None):
    """URL'yi DÜZEN (template) imzasına indirger. Aynı düzenden üretilen sayfalar
    (ör. tüm 'program-hedefleri' sayfaları, tüm bölümlerde) aynı imzayı alır.
    İçeriğe özgü orta segmentler (fakülte/bölüm adı, id) elenir; dil + üst bölüm
    + yaprak SAYFA-TİPİ tutulur. Derinlik (nesting) düzeni belirlemez -> katılmaz
    (aynı sayfa-tipi hangi derinlikte olursa aynı görünür).

    leaf_vocab verilirse (sık tekrar eden sayfa-tipi yaprakları kümesi), bu
    kümede OLMAYAN yaprak segmentler (nadir = varlık adı, ör. fakülte/bölüm adı)
    '*'a indirgenir. Böylece binlerce tekil 'varlık iniş sayfası' tek şablona
    (ör. 'academic|*') toplanır -> 17k sayfa onlarca şablona iner."""
    p = urlparse(url)
    first, last, depth = _leaf_of(url)
    lang = ""
    segs = [s for s in (p.path or "/").split("/") if s]
    if segs and segs[0].lower() in _LANG_SEGS:
        lang = segs[0].lower()
    if not depth:
        return f"{lang}|ROOT"
    if leaf_vocab is not None and last != "*" and last not in leaf_vocab:
        last = "*"                                   # nadir yaprak = varlık adı
    tab = ""
    if p.query:  # sekme/rota farkı (ör. ?tab=...) düzeni değiştirebilir
        q = re.sub(r"=[^&]*", "", p.query)           # sadece anahtarlar
        tab = "?" + re.sub(r"[^a-z0-9&]+", "", q.lower())[:30]
    return f"{lang}|{first}|{last}{tab}"


def load_cluster_counts(source_hint=None):
    """template_clusters.json'u bulur -> (counts{imza:sayfa}, leaf_vocab set). Yoksa (None,None)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for d in ((os.path.dirname(source_hint) or ".") if source_hint else ".",
              ".", "data", os.path.join("..", "data"),
              os.path.join(script_dir, "..", "data"), script_dir):
        fp = os.path.join(d, "template_clusters.json")
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                clusters = data["clusters"] if isinstance(data, dict) and "clusters" in data else data
                counts = {c["signature"]: c["count"] for c in clusters}
                vocab = set(data.get("leaf_vocab", [])) if isinstance(data, dict) else set()
                return counts, (vocab or None)
            except Exception:
                return None, None
    return None, None


# --- Tarayıcı içinde çalışan GÖRSEL DENETİM ----------------------------------
#  Yaklaşım: piksel eşiği KOVALAMAZ. Bir kusuru ancak "kullanıcının gerçekten
#  gördüğü" bir bozukluksa bildirir:
#   • içerik taşması: EKRANDA FİİLEN ÇİZİLEN, metin/görsel İÇEREN, kırpılmayan
#     bir öğe viewport'un sağına taşıyorsa (boş/dekoratif kutular ve gizli
#     paneller elenir -> "boşluk varmış gibi ama yok" yanlış pozitifi biter).
#   • kırık görsel, kırpılan metin, üst üste binen öğeler, boş render.
VISUAL_AUDIT_JS = r"""(opts) => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const defects = [];
  const mkrect = (el) => { const r = el.getBoundingClientRect();
    return {x:Math.round(r.left+window.scrollX), y:Math.round(r.top+window.scrollY),
            w:Math.round(r.width), h:Math.round(r.height)}; };
  const label = (el) => { if(!el) return '';
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#'+el.id;
    else if (typeof el.className==='string' && el.className.trim())
      s += '.'+el.className.trim().split(/\s+/).slice(0,2).join('.');
    return s.slice(0,90); };
  const txt = (el) => el ? ((el.innerText||el.getAttribute('alt')||el.getAttribute('aria-label')||'')
                            .replace(/\s+/g,' ').trim().slice(0,60)) : '';
  const vis = (el,st,r) => { st=st||getComputedStyle(el);
    if(st.display==='none'||st.visibility==='hidden'||parseFloat(st.opacity||'1')===0) return false;
    r=r||el.getBoundingClientRect(); return r.width>0 && r.height>0; };
  const add = (type,el,detail,value,rect) => defects.push({
    type, selector:label(el), text:txt(el), detail, value:String(value),
    rect: rect || (el?mkrect(el):null) });

  const all = [...document.body.querySelectorAll('*')];

  // Yardimci: oge GERCEK icerik mi tasiyor (metin ya da yuklenmis gorsel)?
  const hasContent = (el) => {
    if (el.tagName === 'IMG') return el.naturalWidth > 0;
    if (el.tagName === 'svg' || el.tagName === 'SVG') return true;
    return (el.innerText || '').trim().length > 0;
  };
  // Yardimci: ogenin sag tasmasi bir ust oge tarafindan KAPSANIYOR mu?
  //   hidden/clip -> gorsel kirpma;  auto/scroll -> bilincli kaydirma kutusu
  //   (responsive tablo sarmalayici gibi). Her ikisinde de tasma SAYFAYI
  //   kaydirmaz, kullanici bir kusur gormez -> elenir.
  const contained = (el, r) => {
    let p = el.parentElement;
    while (p) {
      const st = getComputedStyle(p);
      const ox = st.overflowX, o = st.overflow;
      if (ox==='hidden'||ox==='clip'||ox==='auto'||ox==='scroll'||
          o==='hidden'||o==='clip'||o==='auto'||o==='scroll') {
        if (r.right > p.getBoundingClientRect().right + 1) return true;
      }
      p = p.parentElement;
    }
    return false;
  };
  // Yardimci: oge, viewport icinde kalan bir noktasinda FIILEN ekrana ciziliyor mu?
  //   (off-canvas / ortulu / seffaf gizli paneller elenir)
  const paintedInView = (el, r) => {
    if (r.left >= vw || r.right <= 0 || r.top >= vh || r.bottom <= 0) return false;
    const x = Math.min(vw-2, Math.max(2, (Math.max(0,r.left)+Math.min(vw,r.right))/2));
    const y = Math.min(vh-2, Math.max(2, (Math.max(0,r.top)+Math.min(vh,r.bottom))/2));
    const hit = document.elementFromPoint(x, y);
    return !!hit && (hit===el || el.contains(hit) || hit.contains(el));
  };

  // 1) İÇERİK TAŞMASI — kullanicinin gordugu gercek yatay tasma.
  //    Ham geometri/scrollWidth degil; GORUNUR ICERIGI olan, kirpilmayan ve
  //    fiilen cizilen bir ogenin viewport'u asmasi aranir.
  const bleed = [];
  for (const el of all) {
    const st = getComputedStyle(el);
    if (st.position==='fixed' || st.position==='sticky') continue;
    const r = el.getBoundingClientRect();
    if (!vis(el,st,r)) continue;
    if (r.right <= vw + 8) continue;          // viewport'u anlamli sekilde asmiyor
    if (r.left >= vw - 4) continue;           // tumuyle disarda (gizli panel)
    if (!hasContent(el)) continue;            // BOS/dekoratif kutu -> kullanici gormez
    if (contained(el, r)) continue;           // ust oge kirpiyor/kaydiriyor -> sayfa kaymaz
    const inView = r.top < vh && r.bottom > 0;
    if (inView && !paintedInView(el, r)) continue;  // fiilen cizili degil -> atla
    bleed.push(el);
  }
  const bSet = new Set(bleed);
  const leaves = bleed.filter(el => ![...el.children].some(c => bSet.has(c)));  // en icteki icerik
  for (const el of leaves.slice(0,12)) {
    const r = el.getBoundingClientRect();
    add('icerik_tasmasi', el, 'İçerik ekranin sagina tasiyor (kullanici yatay kaydirmak zorunda)',
        Math.round(r.right - vw)+'px tasma');
  }

  // 2) Bos / cokmus render (200 dondugu halde icerik yok)
  const bodyLen = (document.body ? document.body.innerText : '').replace(/\s+/g,'').length;
  if (bodyLen < 15 && document.images.length === 0)
    add('bos_sayfa', null, 'Sayfa neredeyse bos render oldu (metin ve gorsel yok)', bodyLen+' karakter');

  // 3) Kirik gorseller (naturalWidth=0)
  let ic=0;
  for (const img of document.images) {
    if (ic>=15) break;
    if (img.complete && img.naturalWidth===0) {
      const src = img.currentSrc || img.getAttribute('src') || '';
      if (!src || src.startsWith('data:')) continue;
      if (!vis(img)) continue;                // gizli/lazy placeholder degil
      add('kirik_gorsel', img, 'Gorsel yuklenemedi (naturalWidth=0)', src.slice(0,120)); ic++;
    }
  }

  // 4) Metin kutusuna sigmiyor / kesiliyor. Yalniz METIN ogeleri (DIV konteyner
  //    HARIC -> kaydirilabilir nav/marquee yanlis pozitifi olmasin) ve asiri
  //    oranli (marquee/ticker) durumlar elenir.
  let tc=0;
  const TT = ['SPAN','P','A','BUTTON','H1','H2','H3','H4','H5','LI','TD','TH','LABEL','STRONG'];
  for (const el of all) {
    if (tc>=15) break;
    if (!TT.includes(el.tagName)) continue;
    const st = getComputedStyle(el);
    if (!(st.overflow==='hidden'||st.overflowX==='hidden'||st.overflowX==='clip'||st.textOverflow==='ellipsis')) continue;
    if (!vis(el,st)) continue;
    if (el.scrollWidth > el.clientWidth + 6 && el.clientWidth > 24
        && el.scrollWidth < el.clientWidth * 2.5) {          // marquee/ticker degil
      if (!txt(el)) continue;
      add('metin_kirpma', el, 'Metin kutusuna sigmiyor, kesiliyor', el.scrollWidth+'px > '+el.clientWidth+'px'); tc++;
    }
  }

  return defects;
}"""

# Sayfanın kendisi yatay kayıyor mu: belge genişliği görünür alandan büyükse ve
# html/body yatay kaydırmayı kapatmamışsa kullanıcı sayfayı yana kaydırabilir.
SAYFA_GENISLIK_JS = r"""() => {
  const h = document.documentElement, b = document.body;
  const ox = (el) => el ? getComputedStyle(el).overflowX : '';
  const kapali = (v) => v === 'hidden' || v === 'clip';
  const scroll = Math.max(h.scrollWidth, b ? b.scrollWidth : 0);
  const kayiyor = scroll > h.clientWidth + 1 && !kapali(ox(h)) && !kapali(ox(b));
  // Sayfa kayıyorsa onu genişleten öğeyi deneyerek bul: her düzeyde çocukları
  // tek tek gizleyip sayfa genişliğini en çok düşüreni seç ve onun içine in.
  // Konuma bakmak yetmiyor: kendi kutusunda kaydırılan öğeler (breadcrumb),
  // ::before/::after, sıfır genişlikli kutudan taşan metin ve atasının
  // kırpmasından kaçan mutlak konumlu öğeler yanlış ya da hiç sonuç vermiyor.
  let tasiran = null;
  if (kayiyor && b) {
    const genislik = () => Math.max(h.scrollWidth, b.scrollWidth);
    const sx = window.scrollX, sy = window.scrollY;
    const dene = (el) => {
      const eski = el.style.getPropertyValue('display');
      const oncelik = el.style.getPropertyPriority('display');
      el.style.setProperty('display', 'none', 'important');
      const w = genislik();
      if (eski) el.style.setProperty('display', eski, oncelik);
      else el.style.removeProperty('display');
      return w;
    };
    let kutu = b;
    for (let derinlik = 0; derinlik < 60; derinlik++) {
      const once = genislik();
      let enIyi = null, enIyiW = once;
      for (const c of kutu.children) {
        if (getComputedStyle(c).display === 'none') continue;
        const w = dene(c);
        if (w < enIyiW) { enIyi = c; enIyiW = w; }
      }
      if (!enIyi) break;
      kutu = enIyi;
    }
    window.scrollTo(sx, sy);
    for (const e of document.querySelectorAll('[data-genisleten]')) e.removeAttribute('data-genisleten');
    if (kutu !== b) {
      kutu.setAttribute('data-genisleten', '');   // oto_duzelt.py öğeyi bu işaretle bulur
      const el = kutu, st = getComputedStyle(el), r = el.getBoundingClientRect();
      let sel = el.tagName.toLowerCase();
      if (el.id) sel += '#' + el.id;
      else if (typeof el.className === 'string' && el.className.trim())
        sel += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.');
      tasiran = {selector: sel.slice(0, 90), tasma_px: Math.round(scroll - h.clientWidth),
                 y: Math.round(r.top + sy),
                 gorunur: st.visibility !== 'hidden' && parseFloat(st.opacity || '1') > 0,
                 metin: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60),
                 // düzeltme önerisi için ipuçları: satır kırılmasını engelleyen stil var mı,
                 // öğe içerik alanında (.prose) mı
                 ws: st.whiteSpace, display: st.display, owrap: st.overflowWrap,
                 prose: !!el.closest('.prose'),
                 ata: (el.parentElement && typeof el.parentElement.className === 'string')
                      ? el.parentElement.tagName.toLowerCase() + '.' +
                        el.parentElement.className.trim().split(/\s+/).slice(0, 3).join('.') : ''};
    }
  }
  return {scroll, client: h.clientWidth, vw: window.innerWidth,
          html_ox: ox(h), body_ox: ox(b), kayiyor, tasiran};
}"""

# --- Kusurlu bolgeleri kirmizi kutuyla isaretleyip kanit goruntusu almak icin ---
VISUAL_MARK_JS = r"""(defects) => {
  const box = document.createElement('div');
  box.id = '__vaudit_overlay';
  box.style.cssText = 'position:absolute;top:0;left:0;z-index:2147483647;pointer-events:none;';
  for (const d of defects) {
    if (!d.rect || (d.rect.w===0 && d.rect.h===0)) continue;
    const b = document.createElement('div');
    b.style.cssText = 'position:absolute;left:'+d.rect.x+'px;top:'+d.rect.y+'px;width:'+d.rect.w+'px;height:'+
      d.rect.h+'px;border:3px solid #e5484d;background:rgba(229,72,77,.12);box-sizing:border-box;';
    const lab = document.createElement('div');
    lab.textContent = d.type;
    lab.style.cssText = 'position:absolute;left:'+d.rect.x+'px;top:'+Math.max(0,d.rect.y-15)+'px;background:#e5484d;'+
      'color:#fff;font:11px/14px sans-serif;padding:0 4px;white-space:nowrap;';
    box.appendChild(b); box.appendChild(lab);
  }
  document.body.appendChild(box);
}"""


# --------------------------------------------------------------- yardımcılar ---
async def sayfayi_hazirla(page):
    """--kaydir: Tam sayfa görüntüden önce sayfayı adım adım sona kadar kaydırır.
    Aşağı kaydırınca yüklenen görseller (lazy loading) ve ekrana girince başlayan
    sayaç animasyonları tetiklenmezse ekran görüntüsünde boş/0 görünür."""
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.evaluate("""async () => {
        const adim = Math.max(200, window.innerHeight * 0.8);
        for (let y = 0; y < document.body.scrollHeight; y += adim) {
            window.scrollTo(0, y);
            await new Promise(r => setTimeout(r, 250));
        }
        window.scrollTo(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 500));
        window.scrollTo(0, 0);
    }""")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.evaluate("""() => Promise.all([...document.images].filter(i => !i.complete)
        .map(i => new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 5000); })))""")
    await page.wait_for_timeout(1500)   # sayaç animasyonlarının bitmesi için


def safe_name(url, maxlen=110):
    """URL'yi KARARLI (her çalıştırmada aynı) bir dosya adına çevirir.
    Sonuna URL'nin md5 kısaltması eklenir -> farklı URL'ler asla çakışmaz,
    aynı URL her zaman aynı dosya adını alır (parça parça + --resume güvenli)."""
    p = urlparse(url)
    path = (p.path or "/").strip("/")
    q = ("_" + re.sub(r"[^a-zA-Z0-9]+", "-", p.query)) if p.query else ""
    name = re.sub(r"[^a-zA-Z0-9]+", "-", path) + q
    name = name.strip("-") or "anasayfa"
    if len(name) > maxlen:
        name = name[:maxlen]
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return f"{name}-{digest}"


def load_urls(source, limit, offset):
    with open(source, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "url_list" in data:
        urls = data["url_list"]
    elif isinstance(data, dict) and "pages" in data:
        urls = list(data["pages"].keys())
    elif isinstance(data, dict) and "urls" in data:
        urls = data["urls"]
    elif isinstance(data, list):
        urls = [x["url"] if isinstance(x, dict) and "url" in x else x for x in data]
    else:
        urls = list(data)

    clean, seen = [], set()
    for u in urls:
        if not isinstance(u, str) or not u.startswith("http"):
            continue
        # kontrol/high-byte karakter veya boşluk içeren bozuk URL'leri at
        if any(ord(c) < 32 or (ord(c) > 126 and c not in TURKISH_CHARS) for c in u):
            continue
        if " " in u:
            continue
        if u in seen:
            continue
        seen.add(u)
        clean.append(u)

    clean = clean[offset:]
    if limit:
        clean = clean[:limit]
    return clean


# ------------------------------------------------------------- tek sayfa test ---
async def test_page(browser, url, opts, idx, total):
    rec = {
        "index": idx,
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "http_status": None,
        "load_time": None,
        "security": {},
        "turkish": {},
        "accessibility": {},
        "mobile": {},
        "forms": {},
        "console_errors": [],
        "network_errors": [],
        "evidence": {},
        "error": None,
        "overall": "error",
    }
    name = safe_name(url)
    ctx_kwargs = {
        "ignore_https_errors": True,     # self-signed SSL
        "viewport": DESKTOP_VIEWPORT,
        "locale": LOCALE,
        "user_agent": USER_AGENT,
    }
    if opts.video:
        ctx_kwargs["record_video_dir"] = os.path.join(OUT_DIR, "videos")
        ctx_kwargs["record_video_size"] = DESKTOP_VIEWPORT

    context = await browser.new_context(**ctx_kwargs)
    page = await context.new_page()

    console_errors, network_errors = [], []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.on("requestfailed", lambda r: network_errors.append(f"{r.url} ({r.failure})"))

    # --- belge denetimi: ağ yanıtlarından belge tipi dosyaları yakala ---
    doc_hits = {}  # url -> {status, ctype, size, source}

    def _on_response(r):
        if not opts.check_docs:
            return
        try:
            ct = (r.headers.get("content-type") or "").lower()
            u = r.url
            path = u.split("?")[0].lower()
            if any(x in ct for x in DOC_CTYPES) or path.endswith(DOC_EXTS):
                prev = doc_hits.get(u, {})
                doc_hits[u] = {"url": u, "status": r.status, "ctype": ct,
                               "size": r.headers.get("content-length", ""), "source": "network",
                               "referrer": prev.get("referrer", url),
                               "text": prev.get("text", "(ağ isteği)")}
        except Exception:
            pass
    page.on("response", _on_response)

    try:
        start = time.time()
        resp = await page.goto(url, wait_until="load", timeout=opts.timeout * 1000)
        rec["load_time"] = round(time.time() - start, 3)
        rec["http_status"] = resp.status if resp else None
        if getattr(opts, "css_icerik", None):   # --css: önerilen düzeltmeyi canlı sayfaya uygula
            try:
                await page.add_style_tag(content=opts.css_icerik)
                rec["eklenen_css"] = opts.css
            except Exception as e:
                rec["eklenen_css_hata"] = str(e)[:200]

        # --- Güvenlik başlıkları (gerçek yanıttan) ---
        headers = {k.lower(): v for k, v in (resp.headers if resp else {}).items()}
        present = {k: (hdr in headers) for k, hdr in SECURITY_HEADERS.items()}
        rec["security"] = {
            "present": [k for k, v in present.items() if v],
            "missing": [k for k, v in present.items() if not v],
            "all_present": all(present.values()),
        }

        # --- Türkçe karakter (render edilmiş metinden -> doğru) ---
        body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        counts = {c: body_text.count(c) for c in TURKISH_CHARS if body_text.count(c) > 0}
        mojibake = sum(body_text.count(x) for x in ("Ã", "Å", "Ä±", "ÅŸ", "Ã§"))
        rec["turkish"] = {
            "has_turkish": bool(counts),
            "total": sum(counts.values()),
            "sample": dict(sorted(counts.items(), key=lambda x: -x[1])[:5]),
            "mojibake_suspected": mojibake > 5,
        }

        # --- Erişilebilirlik (DOM'dan) ---
        a11y = await page.evaluate("""() => {
            const imgs = [...document.images];
            const noAlt = imgs.filter(i => !i.getAttribute('alt') || !i.getAttribute('alt').trim());
            const h1 = document.querySelectorAll('h1').length;
            const fields = [...document.querySelectorAll('input,select,textarea')]
                .filter(f => !['hidden','submit','button'].includes(f.type));
            let unlabeled = 0;
            for (const f of fields) {
                const id = f.id;
                const lbl = id && document.querySelector(`label[for="${id}"]`);
                if (!lbl && !f.getAttribute('aria-label') && !f.getAttribute('aria-labelledby')) unlabeled++;
            }
            return {
                images_total: imgs.length,
                images_without_alt: noAlt.length,
                h1_count: h1,
                missing_h1: h1 === 0,
                multiple_h1: h1 > 1,
                unlabeled_form_fields: unlabeled,
                has_lang: !!document.documentElement.getAttribute('lang'),
                title: document.title || ''
            };
        }""")
        rec["accessibility"] = a11y

        # --- Formlar ---
        forms = await page.evaluate("""() => {
            return [...document.forms].map(f => ({
                action: f.getAttribute('action') || '',
                method: (f.getAttribute('method')||'get').toLowerCase(),
                fields: f.querySelectorAll('input,select,textarea').length
            }));
        }""")
        rec["forms"] = {"forms_found": len(forms), "detail": forms}

        # --- Mobil / responsive ---
        has_viewport = await page.evaluate("() => !!document.querySelector('meta[name=viewport]')")
        has_media = await page.evaluate("""() => {
            for (const s of document.styleSheets) {
                try {
                    for (const r of s.cssRules) {
                        if (r.type === CSSRule.MEDIA_RULE) return true;
                    }
                } catch(e) {}
            }
            return false;
        }""")

        # --- KANIT: masaüstü ekran görüntüsü ---
        if opts.screenshots and opts.kaydir:
            await sayfayi_hazirla(page)
        if opts.screenshots:
            shot_dir = os.path.join(OUT_DIR, "screenshots")
            desk_path = os.path.join(shot_dir, f"{name}__desktop.png")
            if not (opts.resume and os.path.exists(desk_path)):
                await page.screenshot(path=desk_path, full_page=True)
            rec["evidence"]["desktop"] = os.path.relpath(desk_path, OUT_DIR)

            # tablet görünüm kanıtı (isteğe bağlı)
            if opts.tablet:
                await page.set_viewport_size(TABLET_VIEWPORT)
                await page.wait_for_timeout(400)
                tab_path = os.path.join(shot_dir, f"{name}__tablet.png")
                if not (opts.resume and os.path.exists(tab_path)):
                    await page.screenshot(path=tab_path, full_page=True)
                rec["evidence"]["tablet"] = os.path.relpath(tab_path, OUT_DIR)

            # mobil görünüm kanıtı
            await page.set_viewport_size(MOBILE_VIEWPORT)
            await page.wait_for_timeout(400)
            if opts.kaydir:   # mobil düzende yeni görseller yüklenebilir
                await sayfayi_hazirla(page)
            mob_path = os.path.join(shot_dir, f"{name}__mobile.png")
            if not (opts.resume and os.path.exists(mob_path)):
                await page.screenshot(path=mob_path, full_page=True)
            rec["evidence"]["mobile"] = os.path.relpath(mob_path, OUT_DIR)

        rec["mobile"] = {"has_viewport_meta": has_viewport, "has_media_queries": has_media}

        # --- İsteğe bağlı: GÖRSEL/UI kusur denetimi (HTTP durumundan bağımsız) ---
        # Sayfayı hem masaüstü hem mobil viewport'ta ölçer; DOM geometrisinden
        # görsel bozuklukları (taşma, kırık görsel, kırpılan metin, boş render,
        # küçük dokunma hedefi) tespit eder ve kusurlu bölgeleri işaretli bir
        # ekran görüntüsüyle KANITLAR.
        if opts.check_visual:
            shot_dir = os.path.join(OUT_DIR, "screenshots")
            vis_res = {"desktop": [], "mobile": []}
            genislik = {}
            for vp_name, vp in (("desktop", DESKTOP_VIEWPORT), ("mobile", MOBILE_VIEWPORT)):
                try:
                    await page.set_viewport_size(vp)
                    await page.wait_for_timeout(350)
                    defects = await page.evaluate(VISUAL_AUDIT_JS, {"mobile": vp_name == "mobile"})
                except Exception:
                    defects = []
                try:   # sayfa bütünüyle yana kayıyor mu? (taşmanın kullanıcı açısından tanımı)
                    genislik[vp_name] = await page.evaluate(SAYFA_GENISLIK_JS)
                except Exception:
                    pass
                defects = (defects or [])[:40]
                vis_res[vp_name] = defects
                if defects:  # kusur varsa işaretli kanıt görüntüsü üret
                    try:
                        await page.evaluate(VISUAL_MARK_JS, defects)
                        vpath = os.path.join(shot_dir, f"{name}__visual-{vp_name}.png")
                        await page.screenshot(path=vpath, full_page=True)
                        await page.evaluate(
                            "() => { const o=document.getElementById('__vaudit_overlay'); if(o) o.remove(); }")
                        rec["evidence"][f"vshot_{vp_name}"] = os.path.relpath(vpath, OUT_DIR)
                    except Exception:
                        pass
            alld = vis_res["desktop"] + vis_res["mobile"]
            rec["visual"] = {
                "sayfa_genislik": genislik,
                "desktop": vis_res["desktop"],
                "mobile": vis_res["mobile"],
                "defect_count": len(alld),
                "types": dict(Counter(d["type"] for d in alld)),
            }

        # --- İsteğe bağlı: sayfadaki linkleri (metniyle birlikte) topla ---
        if opts.check_links:
            links = await page.evaluate("""() => [...document.querySelectorAll('a[href]')].map(a => ({
                href: a.href,
                text: (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').trim().slice(0,90)
            }))""")
            seen = {}
            for l in links:
                h = l.get("href", "")
                if h.startswith("http") and not h.lower().startswith(NON_HTTP_SCHEMES):
                    seen.setdefault(h, l.get("text", ""))
            rec["_collected_links"] = [{"url": h, "text": t, "referrer": url} for h, t in seen.items()]
            rec["links_on_page"] = len(rec["_collected_links"])

        # --- İsteğe bağlı: belge/dosya linklerini DOM'dan (metin+kaynak sayfa) topla ---
        if opts.check_docs:
            dom_docs = await page.evaluate("""() => {
                const out = [];
                const push = (u, t) => { if (u) out.push({href:u, text:(t||'').trim().slice(0,90)}); };
                document.querySelectorAll('a[href]').forEach(a => {
                    const h = a.getAttribute('href') || '';
                    const t = (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '');
                    if (a.hasAttribute('download') || /\\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z|csv|txt|rtf|od[tsp])(\\?|$)/i.test(h))
                        push(a.href || h, t);
                    if (h.toLowerCase().startsWith('file:')) push(h, t);
                });
                document.querySelectorAll('iframe[src],embed[src],object[data]').forEach(e => {
                    const s = e.getAttribute('src') || e.getAttribute('data') || '';
                    if (/\\.(pdf|docx?|xlsx?|pptx?)(\\?|$)/i.test(s)) push(new URL(s, location.href).href, '(gomulu icerik)');
                });
                return out;
            }""")
            for d in dom_docs:
                u = d.get("href", ""); text = d.get("text", "")
                if u.lower().startswith("file:"):
                    doc_hits.setdefault(u, {"url": u, "status": "LEAKED", "ctype": "yerel-dosya-yolu",
                                            "size": "", "source": "dom(file:)", "referrer": url, "text": text})
                elif u not in doc_hits:
                    doc_hits[u] = {"url": u, "status": None, "ctype": "", "size": "", "source": "dom",
                                   "referrer": url, "text": text}
                else:
                    # ağdan gelmiş ama metin/kaynak boşsa doldur
                    doc_hits[u].setdefault("referrer", url); doc_hits[u].setdefault("text", text)
            rec["_docs"] = list(doc_hits.values())

        # --- konsol hatalarını sınıflandır (gerçek JS vs kaynak yükleme) ---
        # "Failed to load resource" = alt kaynak 404/403 (çoğu zaman sayfanın
        # kendi HTTP durumuyla örtüşür, gürültü). Geri kalanı gerçek JS/React hatası.
        js_errors, resource_errors = [], []
        for e in console_errors:
            (resource_errors if "Failed to load resource" in e else js_errors).append(e)
        hydration = any("#418" in e or "#423" in e or "#425" in e or "Hydration" in e or "hydrat" in e.lower()
                        for e in js_errors)
        rec["console_errors"] = console_errors[:20]
        rec["js_errors"] = js_errors[:20]
        rec["resource_errors"] = resource_errors[:20]
        rec["hydration_error"] = hydration
        rec["network_errors"] = network_errors[:20]

        # --- genel değerlendirme (yalnızca GERÇEK JS hatası WARN sayılır) ---
        ok = rec["http_status"] == 200
        warns = (rec["accessibility"].get("images_without_alt", 0) > 0
                 or rec["accessibility"].get("missing_h1")
                 or rec["turkish"].get("mojibake_suspected")
                 or js_errors
                 or rec.get("visual", {}).get("defect_count"))
        rec["overall"] = "pass" if ok and not warns else ("warn" if ok else "fail")

    except Exception as e:
        rec["error"] = str(e)
        rec["overall"] = "fail" if rec["http_status"] else "error"
    finally:
        await page.close()
        await context.close()
        if opts.video:
            try:
                # video dosyasını sayfa adına göre yeniden adlandır
                vids = [f for f in os.listdir(os.path.join(OUT_DIR, "videos")) if f.endswith(".webm")]
                # en yeni videoyu bu sayfaya ata
                if vids:
                    vdir = os.path.join(OUT_DIR, "videos")
                    newest = max(vids, key=lambda f: os.path.getmtime(os.path.join(vdir, f)))
                    target = os.path.join(vdir, f"{name}.webm")
                    if newest != f"{name}.webm":
                        os.replace(os.path.join(vdir, newest), target)
                    rec["evidence"]["video"] = os.path.relpath(target, OUT_DIR)
            except Exception:
                pass

    print(f"  [{idx}/{total}] {rec['overall'].upper():5} {rec['http_status']}  {url[:80]}")
    return rec


# ---------------------------------------------------------------- link denetim ---
async def check_broken_links(pw_request, results, timeout):
    # link -> (kaynak_sayfa, buton_metni) — ilk görülen sayfayı sakla
    sources = {}
    for r in results:
        for d in r.get("_collected_links", []):
            if isinstance(d, dict):
                sources.setdefault(d["url"], (d.get("referrer", ""), d.get("text", "")))
            else:  # eski format (düz url)
                sources.setdefault(d, ("", ""))
    broken = []
    print(f"\n[*] {len(sources)} tekil link kontrol ediliyor...")
    ctx = await pw_request.new_context(ignore_https_errors=True)
    for i, u in enumerate(sorted(sources), 1):
        ref, text = sources[u]
        try:
            resp = await ctx.get(u, timeout=timeout * 1000)
            if resp.status >= 400:
                broken.append({"url": u, "status": resp.status, "referrer": ref, "text": text})
        except Exception as e:
            broken.append({"url": u, "status": f"error: {e}", "referrer": ref, "text": text})
        if i % 100 == 0:
            print(f"    {i}/{len(sources)} ({len(broken)} kırık)")
    await ctx.dispose()
    return broken


# ------------------------------------------------------------ belge denetim ---
async def audit_documents(pw_request, results, timeout):
    """Toplanan belge/dosya linklerini birleştirir, erişilebilirliğini kontrol eder.
    Döndürür: her belge için {url, status, ctype, size, source, flag}."""
    merged = {}
    for r in results:
        for d in r.get("_docs", []):
            u = d["url"]
            # network kaynağı (status/ctype dolu) DOM kaydının üstüne yazsın
            if u not in merged or (d.get("status") not in (None, "")):
                merged[u] = dict(d)

    to_check = [u for u, d in merged.items()
                if d.get("status") in (None, "") and not u.lower().startswith("file:")]
    print(f"\n[*] {len(merged)} belge/dosya linki ({len(to_check)} tanesi HTTP kontrol edilecek)...")
    ctx = await pw_request.new_context(ignore_https_errors=True)
    for i, u in enumerate(to_check, 1):
        try:
            resp = await ctx.get(u, timeout=timeout * 1000)
            merged[u]["status"] = resp.status
            merged[u]["ctype"] = (resp.headers.get("content-type") or "").lower()
            merged[u]["size"] = resp.headers.get("content-length", "")
        except Exception as e:
            merged[u]["status"] = f"error: {e}"
        if i % 50 == 0:
            print(f"    {i}/{len(to_check)}")
    await ctx.dispose()

    out = []
    for d in merged.values():
        st = d.get("status")
        if str(st).startswith("file:") or d.get("source") == "dom(file:)" or d["url"].lower().startswith("file:"):
            d["flag"] = "SIZDIRILMIS YEREL DOSYA YOLU (kirik + bilgi sizintisi)"
        elif isinstance(st, int) and st >= 400:
            d["flag"] = "KIRIK/ERISILEMIYOR"
        elif str(st).startswith("error"):
            d["flag"] = "ULASILAMADI"
        else:
            d["flag"] = "erisilebilir"
        out.append(d)
    return out


# --------------------------------------------------------------- HTML raporu ---
def build_html_report(results, meta):
    def badge(s):
        color = {"pass": "#1a7f37", "warn": "#9a6700", "fail": "#cf222e", "error": "#57606a"}.get(s, "#57606a")
        return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{s.upper()}</span>'

    dist = Counter(r["overall"] for r in results)
    rows = []
    for r in results:
        ev = r.get("evidence", {})
        thumbs = ""
        if ev.get("desktop"):
            thumbs += f'<a href="{html.escape(ev["desktop"])}" target="_blank"><img loading="lazy" decoding="async" src="{html.escape(ev["desktop"])}" class="thumb" title="Masaüstü"></a>'
        if ev.get("tablet"):
            thumbs += f'<a href="{html.escape(ev["tablet"])}" target="_blank"><img loading="lazy" decoding="async" src="{html.escape(ev["tablet"])}" class="thumb thumb-m" title="Tablet"></a>'
        if ev.get("mobile"):
            thumbs += f'<a href="{html.escape(ev["mobile"])}" target="_blank"><img loading="lazy" decoding="async" src="{html.escape(ev["mobile"])}" class="thumb thumb-m" title="Mobil"></a>'
        if ev.get("video"):
            thumbs += f'<a href="{html.escape(ev["video"])}" target="_blank">🎬 video</a>'
        a11y = r.get("accessibility", {})
        sec = r.get("security", {})
        tr = r.get("turkish", {})
        issues = []
        if r.get("http_status") != 200:
            issues.append(f"HTTP {r.get('http_status')}")
        if a11y.get("images_without_alt"):
            issues.append(f"{a11y['images_without_alt']} alt-yok")
        if a11y.get("missing_h1"):
            issues.append("H1 yok")
        if tr.get("mojibake_suspected"):
            issues.append("mojibake")
        if r.get("hydration_error"):
            issues.append("⚠ React hydration (#418)")
        if r.get("js_errors"):
            issues.append(f"{len(r['js_errors'])} JS-hata")
        if r.get("resource_errors"):
            issues.append(f"{len(r['resource_errors'])} kaynak-404/403")
        if sec.get("missing"):
            issues.append(f"{len(sec['missing'])} güvenlik-başlığı-eksik")
        # hızlı filtre için etiketler ve aranabilir metin
        flags = [r["overall"]]
        if r.get("http_status") == 404: flags.append("h404")
        if r.get("http_status") == 403: flags.append("h403")
        if r.get("hydration_error"): flags.append("hyd")
        if a11y.get("images_without_alt"): flags.append("alt")
        if a11y.get("missing_h1"): flags.append("h1")
        if r.get("js_errors"): flags.append("js")
        if tr.get("mojibake_suspected"): flags.append("moji")
        flagstr = " ".join(flags)
        search = html.escape(r["url"].lower())
        rows.append(f'<tr class="row-{r["overall"]}" data-f="{flagstr}" data-s="{search}">'
            f'<td>{r["index"]}</td>'
            f'<td class="url"><a href="{html.escape(r["url"])}" target="_blank">{html.escape(r["url"])}</a></td>'
            f'<td>{badge(r["overall"])}</td>'
            f'<td>{r.get("http_status","")}</td>'
            f'<td>{r.get("load_time","")}</td>'
            f'<td>{"✔" if tr.get("has_turkish") else "—"}{" ⚠" if tr.get("mojibake_suspected") else ""}</td>'
            f'<td>{html.escape(", ".join(issues))}</td>'
            f'<td class="ev">{thumbs}</td></tr>')

    cond_rows = "".join(f"<tr><td><b>{html.escape(t)}</b></td><td>{html.escape(d)}</td></tr>" for t, d in TEST_CONDITIONS)

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>{html.escape(SITE_NAME)} — Kanıtlı Test Raporu</title>
<style>
  body {{ font-family: system-ui, Arial, sans-serif; margin: 0; color: #1f2328; background:#f6f8fa; }}
  header {{ background:#0b3d66; color:#fff; padding:20px 28px; }}
  header h1 {{ margin:0 0 4px; font-size:22px; }}
  .meta {{ font-size:13px; opacity:.9; }}
  .wrap {{ padding: 20px 28px; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:18px; }}
  .card {{ background:#fff; border:1px solid #d0d7de; border-radius:10px; padding:14px 18px; min-width:120px; }}
  .card b {{ font-size:26px; display:block; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13px; }}
  th, td {{ border:1px solid #d0d7de; padding:6px 8px; text-align:left; vertical-align:top; }}
  th {{ background:#eaeef2; position:sticky; top:0; }}
  .url {{ max-width:340px; word-break:break-all; }}
  .thumb {{ height:70px; border:1px solid #ccc; border-radius:4px; margin:2px; }}
  .thumb-m {{ height:70px; }}
  .row-fail {{ background:#fff0f0; }}
  .row-warn {{ background:#fffbe6; }}
  .row-error {{ background:#f2f2f2; }}
  input#f {{ padding:8px; width:300px; border:1px solid #ccc; border-radius:6px; }}
  details {{ background:#fff; border:1px solid #d0d7de; border-radius:10px; padding:12px 16px; margin-bottom:18px; }}
  .chip {{ display:inline-block; padding:5px 11px; margin:2px; border:1px solid #d0d7de; border-radius:16px;
    background:#fff; cursor:pointer; font-size:13px; user-select:none; }}
  .chip.active {{ background:#0b3d66; color:#fff; border-color:#0b3d66; }}
  .bar {{ margin-bottom:10px; display:flex; flex-wrap:wrap; gap:4px; align-items:center; }}
  #more {{ padding:8px 16px; margin:14px auto; display:block; border:1px solid #0b3d66; background:#fff;
    color:#0b3d66; border-radius:8px; cursor:pointer; font-size:14px; }}
  #cnt {{ font-size:13px; color:#57606a; margin-left:8px; }}
</style></head>
<body>
<header>
  <h1>{html.escape(SITE_NAME)} Web Sitesi — Kanıtlı Kapsamlı Test Raporu</h1>
  <div class="meta">Hedef: {html.escape(meta['base'])} · Tarih: {meta['date']} · Tarayıcı: {html.escape(meta['browser'])}
   · Test edilen sayfa: {meta['count']} · Masaüstü {DESKTOP_VIEWPORT['width']}×{DESKTOP_VIEWPORT['height']}, Mobil {MOBILE_VIEWPORT['width']}×{MOBILE_VIEWPORT['height']}</div>
</header>
<div class="wrap">
  <div class="cards">
    <div class="card"><b>{meta['count']}</b>Toplam sayfa</div>
    <div class="card" style="color:#1a7f37"><b>{dist.get('pass',0)}</b>PASS</div>
    <div class="card" style="color:#9a6700"><b>{dist.get('warn',0)}</b>WARN</div>
    <div class="card" style="color:#cf222e"><b>{dist.get('fail',0)}</b>FAIL</div>
    <div class="card" style="color:#57606a"><b>{dist.get('error',0)}</b>ERROR</div>
  </div>

  <details><summary><b>Test Koşulları (bu raporda neler test edildi)</b></summary>
    <table style="margin-top:10px">{cond_rows}</table>
    <p style="font-size:12px;color:#57606a">Not: Küçük resimler tıklanınca tam boyut açılır (kanıt).
    Ekran görüntüleri <code>screenshots/</code>, videolar <code>videos/</code> klasöründedir.</p>
  </details>

  <div class="bar">
    <span class="chip active" data-flag="all">Tümü</span>
    <span class="chip" data-flag="fail">FAIL</span>
    <span class="chip" data-flag="warn">WARN</span>
    <span class="chip" data-flag="pass">PASS</span>
    <span class="chip" data-flag="error">ERROR</span>
    <span class="chip" data-flag="hyd">React #418</span>
    <span class="chip" data-flag="h404">404</span>
    <span class="chip" data-flag="h403">403</span>
    <span class="chip" data-flag="alt">alt-yok</span>
    <span class="chip" data-flag="h1">H1-yok</span>
    <span class="chip" data-flag="js">JS-hata</span>
  </div>
  <div class="bar">
    <input id="f" placeholder="URL ara (ör: /haberler, akademik)" oninput="deb()">
    <span id="cnt"></span>
  </div>
  <table id="t">
    <thead><tr>
      <th>#</th><th>URL</th><th>Sonuç</th><th>HTTP</th><th>Süre(s)</th><th>TR</th><th>Bulgular</th><th>Kanıt</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <button id="more" onclick="grow()">Daha fazla göster (+400)</button>
</div>
<script>
var STEP=400, limit=STEP, flag="all", q="", tId=null;
var ROWS=[].slice.call(document.querySelectorAll('#t tbody tr'));
function apply(){{
  var shown=0, matched=0;
  for(var i=0;i<ROWS.length;i++){{
    var r=ROWS[i];
    var ok=(flag==="all"||(" "+r.getAttribute("data-f")+" ").indexOf(" "+flag+" ")>=0)
         &&(q===""||r.getAttribute("data-s").indexOf(q)>=0);
    if(ok){{ matched++; if(shown<limit){{ r.style.display=""; shown++; }} else r.style.display="none"; }}
    else r.style.display="none";
  }}
  document.getElementById('cnt').textContent=matched+" eşleşme · "+shown+" gösteriliyor";
  document.getElementById('more').style.display=(shown<matched)?"block":"none";
}}
function grow(){{ limit+=STEP; apply(); }}
function deb(){{ clearTimeout(tId); tId=setTimeout(function(){{ q=document.getElementById('f').value.toLowerCase(); limit=STEP; apply(); }},180); }}
document.querySelectorAll('.chip').forEach(function(c){{
  c.onclick=function(){{
    document.querySelectorAll('.chip').forEach(function(x){{x.classList.remove('active');}});
    c.classList.add('active'); flag=c.getAttribute('data-flag'); limit=STEP; apply();
  }};
}});
apply();
</script>
</body></html>"""


# ------------------------------------------------------------- görsel raporu ---
def _visual_rows(results):
    """results -> görsel kusur satırları [{url, viewport, type, detail, value, selector, text}]."""
    rows = []
    for r in results:
        v = r.get("visual") or {}
        for vp_name, vp_tr in (("desktop", "masaüstü"), ("mobile", "mobil")):
            for d in v.get(vp_name, []):
                rows.append({"url": r["url"], "viewport": vp_tr, "type": d.get("type", ""),
                             "detail": d.get("detail", ""), "value": d.get("value", ""),
                             "selector": d.get("selector", ""), "text": d.get("text", "")})
    return rows


def build_visual_report(results, meta, cluster=None):
    """Görsel/UI kusurlarını filtreli, işaretli-görsel kanıtlı bir HTML rapora dönüştürür.
    cluster=(counts, leaf_vocab) verilirse rapor ŞABLON seviyesinde özetlenir:
    her kusur, ait olduğu düzenin kaç sayfayı etkilediğiyle birlikte gösterilir."""
    pages = [r for r in results if (r.get("visual") or {}).get("defect_count")]
    pages.sort(key=lambda r: -r["visual"]["defect_count"])
    total_def = sum(r["visual"]["defect_count"] for r in pages)
    scanned = sum(1 for r in results if "visual" in r)
    type_counter = Counter()
    for r in pages:
        for vp in ("desktop", "mobile"):
            for d in r["visual"].get(vp, []):
                type_counter[d["type"]] += 1

    def tlabel(t):
        return VISUAL_TYPES.get(t, (t, "#57606a", "orta"))[0]

    def tcolor(t):
        return VISUAL_TYPES.get(t, (t, "#57606a", "orta"))[1]

    # --- ŞABLON kümeleme (varsa): her sayfayı düzenine bağla ---
    counts, vocab = (cluster or (None, None))
    have_cluster = counts is not None

    def sig_of(url):
        return template_signature(url, vocab) if have_cluster else url

    def affected_of(url):
        return counts.get(sig_of(url), 1) if have_cluster else 1

    # şablon başına özet: temsilci-kusur sayısı, etkilenen toplam sayfa, türler, örnek
    rollup = {}
    for r in pages:
        sig = sig_of(r["url"])
        e = rollup.setdefault(sig, {"reps": 0, "affected": affected_of(r["url"]),
                                    "types": set(), "example": r})
        e["reps"] += 1
        for vp in ("desktop", "mobile"):
            for d in r["visual"].get(vp, []):
                e["types"].add(d["type"])
    total_affected = sum(e["affected"] for e in rollup.values())

    chip_bar = ['<span class="chip active" data-flag="all">Tümü</span>']
    for t, n in type_counter.most_common():
        chip_bar.append(f'<span class="chip" data-flag="{html.escape(t)}">{html.escape(tlabel(t))} ({n})</span>')
    chips_html = "".join(chip_bar)

    rows = []
    for r in pages:
        v, ev = r["visual"], r.get("evidence", {})
        alld = [("masaüstü", d) for d in v.get("desktop", [])] + [("mobil", d) for d in v.get("mobile", [])]
        types = sorted({d["type"] for _, d in alld})
        badges = "".join(f'<span style="background:{tcolor(t)};color:#fff;padding:1px 7px;border-radius:9px;'
                         f'font-size:11px;margin:1px;display:inline-block">{html.escape(tlabel(t))}</span>' for t in types)
        thumbs = ""
        if ev.get("vshot_desktop"):
            thumbs += (f'<a href="{html.escape(ev["vshot_desktop"])}" target="_blank">'
                       f'<img loading="lazy" decoding="async" src="{html.escape(ev["vshot_desktop"])}" '
                       f'class="thumb" title="Masaüstü (işaretli kanıt)"></a>')
        if ev.get("vshot_mobile"):
            thumbs += (f'<a href="{html.escape(ev["vshot_mobile"])}" target="_blank">'
                       f'<img loading="lazy" decoding="async" src="{html.escape(ev["vshot_mobile"])}" '
                       f'class="thumb thumb-m" title="Mobil (işaretli kanıt)"></a>')
        det = "".join(
            f"<li><b>{vp}</b> · <code>{html.escape(d['type'])}</code> — {html.escape(d['detail'])} "
            f"<i>({html.escape(d['value'])})</i>"
            + (f" · <code>{html.escape(d['selector'])}</code>" if d.get('selector') else "")
            + (f" · &ldquo;{html.escape(d['text'])}&rdquo;" if d.get('text') else "") + "</li>"
            for vp, d in alld)
        dataf = " ".join(types)
        aff = affected_of(r["url"])
        aff_html = (f'<span class="aff" title="Bu düzeni kullanan sayfa sayısı">şablon ≈{aff} sayfa</span>'
                    if have_cluster else "")
        rows.append(
            f'<tr data-f="{html.escape(dataf)}" data-s="{html.escape(r["url"].lower())}">'
            f'<td class="url"><a href="{html.escape(r["url"])}" target="_blank">{html.escape(r["url"])}</a> {aff_html}'
            f'<details><summary>{v["defect_count"]} kusur — dök</summary><ul>{det}</ul></details></td>'
            f'<td>{badges}</td><td class="ev">{thumbs}</td></tr>')

    # --- ŞABLON ÖZET tablosu (varsa): en çok sayfayı etkileyen düzenler önce ---
    rollup_html = ""
    if have_cluster and rollup:
        rr = []
        for sig, e in sorted(rollup.items(), key=lambda kv: -kv[1]["affected"]):
            ex = e["example"]; ev = ex.get("evidence", {})
            badges = "".join(f'<span style="background:{tcolor(t)};color:#fff;padding:1px 7px;'
                             f'border-radius:9px;font-size:11px;margin:1px;display:inline-block">'
                             f'{html.escape(tlabel(t))}</span>' for t in sorted(e["types"]))
            thumb = ""
            for k, ttl in (("vshot_mobile", "Mobil"), ("vshot_desktop", "Masaüstü")):
                if ev.get(k):
                    thumb = (f'<a href="{html.escape(ev[k])}" target="_blank"><img loading="lazy" '
                             f'src="{html.escape(ev[k])}" class="thumb thumb-m" title="{ttl} (işaretli)"></a>')
                    break
            rr.append(
                f'<tr><td><b>≈{e["affected"]}</b></td><td><code>{html.escape(sig)}</code></td>'
                f'<td>{badges}</td>'
                f'<td class="url"><a href="{html.escape(ex["url"])}" target="_blank">{html.escape(ex["url"])}</a></td>'
                f'<td class="ev">{thumb}</td></tr>')
        rollup_html = f"""
  <h2 style="margin:18px 0 8px">Şablon özeti — tek düzeltme çok sayfayı çözer</h2>
  <p style="font-size:13px;color:#57606a;margin:0 0 8px">Kusurlar düzen (template) seviyesindedir.
   Aşağıdaki her satır bir düzeni ve o düzeni kullanan <b>tahmini sayfa sayısını</b> gösterir;
   düzeni bir kez düzeltmek o kadar sayfayı çözer. Sıralama etkilenen sayfa sayısına göre.</p>
  <table>
    <thead><tr><th>≈Etkilenen sayfa</th><th>Düzen imzası</th><th>Kusur türleri</th>
      <th>Örnek sayfa</th><th>İşaretli kanıt</th></tr></thead>
    <tbody>{''.join(rr)}</tbody>
  </table>
  <h2 style="margin:22px 0 8px">Temsilci sayfa dökümü</h2>"""

    cond = "".join(f"<tr><td><b>{html.escape(l)}</b></td><td>{html.escape(o)}</td></tr>"
                   for t, (l, c, o) in VISUAL_TYPES.items())

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>{html.escape(SITE_NAME)} — Görsel/UI Kusur Raporu</title>
<style>
  body {{ font-family: system-ui, Arial, sans-serif; margin:0; color:#1f2328; background:#f6f8fa; }}
  header {{ background:#6b1f66; color:#fff; padding:20px 28px; }}
  header h1 {{ margin:0 0 4px; font-size:22px; }}
  .meta {{ font-size:13px; opacity:.9; }}
  .wrap {{ padding:20px 28px; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:18px; }}
  .card {{ background:#fff; border:1px solid #d0d7de; border-radius:10px; padding:14px 18px; min-width:120px; }}
  .card b {{ font-size:26px; display:block; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13px; }}
  th, td {{ border:1px solid #d0d7de; padding:6px 8px; text-align:left; vertical-align:top; }}
  th {{ background:#eaeef2; position:sticky; top:0; }}
  .url {{ max-width:420px; word-break:break-all; }}
  .thumb {{ height:80px; border:1px solid #ccc; border-radius:4px; margin:2px; }}
  .thumb-m {{ height:80px; }}
  details {{ margin-top:6px; }} summary {{ cursor:pointer; color:#6b1f66; font-size:12px; }}
  details ul {{ margin:6px 0 0 16px; padding:0; font-size:12px; }}
  .chip {{ display:inline-block; padding:5px 11px; margin:2px; border:1px solid #d0d7de; border-radius:16px;
    background:#fff; cursor:pointer; font-size:13px; user-select:none; }}
  .chip.active {{ background:#6b1f66; color:#fff; border-color:#6b1f66; }}
  .bar {{ margin-bottom:10px; display:flex; flex-wrap:wrap; gap:4px; align-items:center; }}
  input#f {{ padding:8px; width:300px; border:1px solid #ccc; border-radius:6px; }}
  #more {{ padding:8px 16px; margin:14px auto; display:block; border:1px solid #6b1f66; background:#fff;
    color:#6b1f66; border-radius:8px; cursor:pointer; font-size:14px; }}
  #cnt {{ font-size:13px; color:#57606a; margin-left:8px; }}
  .info {{ background:#fff; border:1px solid #d0d7de; border-radius:10px; padding:12px 16px; margin-bottom:18px; }}
  .aff {{ display:inline-block; background:#f2e9f1; color:#6b1f66; border:1px solid #dcc6da;
    border-radius:9px; padding:1px 7px; font-size:11px; white-space:nowrap; }}
  h2 {{ font-size:17px; }}
</style></head>
<body>
<header>
  <h1>{html.escape(SITE_NAME)} — Görsel / UI Kusur Raporu</h1>
  <div class="meta">Hedef: {html.escape(meta['base'])} · Tarih: {meta['date']}
   · Taranan sayfa: {scanned} · Masaüstü {DESKTOP_VIEWPORT['width']}×{DESKTOP_VIEWPORT['height']},
   Mobil {MOBILE_VIEWPORT['width']}×{MOBILE_VIEWPORT['height']} · HTTP durumundan bağımsız görsel denetim</div>
</header>
<div class="wrap">
  <div class="cards">
    <div class="card"><b>{scanned}</b>Taranan temsilci</div>
    <div class="card" style="color:#cf222e"><b>{len(pages)}</b>Kusurlu temsilci</div>
    {(f'<div class="card" style="color:#6b1f66"><b>{len(rollup)}</b>Kusurlu düzen (şablon)</div>'
      f'<div class="card" style="color:#6b1f66"><b>≈{total_affected}</b>Etkilenen sayfa</div>') if have_cluster else ''}
    <div class="card"><b>{total_def}</b>Toplam kusur</div>
    <div class="card"><b>{len(type_counter)}</b>Kusur türü</div>
  </div>
  <details class="info"><summary><b>Bu rapor neyi tespit eder?</b></summary>
    <table style="margin-top:10px">{cond}</table>
    <p style="font-size:12px;color:#57606a">İşaretli görsellerde kusurlu bölge <b style="color:#e5484d">kırmızı kutu</b>
    ile gösterilir. Küçük resme tıkla → tam boyut kanıt. Ölçümler gerçek tarayıcıda (Chromium) DOM geometrisinden alınır;
    HTTP durumu 200 olsa bile görsel bozukluk yakalanır.</p>
  </details>
  {rollup_html}
  <div class="bar">{chips_html}</div>
  <div class="bar"><input id="f" placeholder="URL ara (ör: /haberler, akademik)" oninput="deb()"><span id="cnt"></span></div>
  <table id="t">
    <thead><tr><th>URL (kusur dökümü)</th><th>Kusur türleri</th><th>İşaretli kanıt (masaüstü / mobil)</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <button id="more" onclick="grow()">Daha fazla göster (+300)</button>
</div>
<script>
var STEP=300, limit=STEP, flag="all", q="", tId=null;
var ROWS=[].slice.call(document.querySelectorAll('#t tbody tr'));
function apply(){{
  var shown=0, matched=0;
  for(var i=0;i<ROWS.length;i++){{
    var r=ROWS[i];
    var ok=(flag==="all"||(" "+r.getAttribute("data-f")+" ").indexOf(" "+flag+" ")>=0)
         &&(q===""||r.getAttribute("data-s").indexOf(q)>=0);
    if(ok){{ matched++; if(shown<limit){{ r.style.display=""; shown++; }} else r.style.display="none"; }}
    else r.style.display="none";
  }}
  document.getElementById('cnt').textContent=matched+" eşleşme · "+shown+" gösteriliyor";
  document.getElementById('more').style.display=(shown<matched)?"block":"none";
}}
function grow(){{ limit+=STEP; apply(); }}
function deb(){{ clearTimeout(tId); tId=setTimeout(function(){{ q=document.getElementById('f').value.toLowerCase(); limit=STEP; apply(); }},180); }}
document.querySelectorAll('.chip').forEach(function(c){{
  c.onclick=function(){{
    document.querySelectorAll('.chip').forEach(function(x){{x.classList.remove('active');}});
    c.classList.add('active'); flag=c.getAttribute('data-flag'); limit=STEP; apply();
  }};
}});
apply();
</script>
</body></html>"""


# ----------------------------------------------------------------------- main ---
def _regenerate_reports(results, meta):
    """results listesinden report.html + report.xlsx + summary.txt üretir (test yok)."""
    with open(os.path.join(OUT_DIR, "report.html"), "w", encoding="utf-8") as f:
        f.write(build_html_report(results, meta))
    # görsel veri varsa görsel raporu da tazele
    if any("visual" in r for r in results):
        vrows = _visual_rows(results)
        with open(os.path.join(OUT_DIR, "gorsel_denetim.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["url", "gorunum", "kusur_turu", "aciklama", "olculen_deger", "css_secici", "metin"])
            for v in vrows:
                w.writerow([v["url"], v["viewport"], v["type"], v["detail"], v["value"], v["selector"], v["text"]])
        with open(os.path.join(OUT_DIR, "gorsel_rapor.html"), "w", encoding="utf-8") as f:
            f.write(build_visual_report(results, meta, cluster=load_cluster_counts()))
    dist = Counter(r.get("overall") for r in results)
    with open(os.path.join(OUT_DIR, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(f"Rapor yeniden üretildi: {datetime.now().isoformat()}\n"
                f"Toplam sayfa: {len(results)}\nSonuç dağılımı: {dict(dist)}\n")
    try:
        import pandas as pd
        rows = []
        for r in results:
            a = r.get("accessibility", {})
            rows.append({"index": r.get("index"), "url": r.get("url"), "overall": r.get("overall"),
                         "http_status": r.get("http_status"), "load_time": r.get("load_time"),
                         "images_no_alt": a.get("images_without_alt"), "missing_h1": a.get("missing_h1"),
                         "hydration_error": r.get("hydration_error"),
                         "sec_missing": ",".join(r.get("security", {}).get("missing", []))})
        pd.DataFrame(rows).to_excel(os.path.join(OUT_DIR, "report.xlsx"), index=False)
    except Exception as e:
        print(f"[!] Excel yazılamadı ({e})")


def site_base(url):
    """Bir adresin kök adresi (https://alan.adi) — rapor başlığındaki 'base' bilgisi."""
    p = urlparse(url or "")
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else BASE_URL


def site_adini_tamamla():
    """Site adı verilmediyse alan adını kullan (ör. www.ornek.edu.tr)."""
    global SITE_NAME
    if not SITE_NAME:
        SITE_NAME = urlparse(BASE_URL).netloc or "Web sitesi"


def apply_site_options(opts):
    """Siteye özgü ayarları (ad, yerel ayar, User-Agent) genel değişkenlere uygula."""
    global SITE_NAME, LOCALE, USER_AGENT
    SITE_NAME = opts.site_adi or SITE_NAME
    LOCALE = opts.locale or LOCALE
    USER_AGENT = opts.user_agent or USER_AGENT


async def run(opts):
    global OUT_DIR, BASE_URL
    OUT_DIR = opts.out_dir
    apply_site_options(opts)
    opts.css_icerik = None
    if opts.css:
        with open(opts.css, encoding="utf-8") as f:
            opts.css_icerik = f.read()
        print(f"[*] CSS ekleniyor: {opts.css}")
    for sub in ("screenshots", "videos"):
        os.makedirs(os.path.join(OUT_DIR, sub), exist_ok=True)

    # --- SADECE RAPOR: testi çalıştırma, mevcut results.jsonl'den yeniden üret ---
    if opts.report_only:
        jl = os.path.join(OUT_DIR, "results.jsonl")
        if not os.path.exists(jl):
            print(f"[HATA] {jl} bulunamadı; önce test çalıştır.")
            sys.exit(1)
        results = []
        with open(jl, encoding="utf-8") as f:
            for line in f:
                try:
                    results.append(json.loads(line))
                except Exception:
                    pass
        for i, r in enumerate(results, 1):
            r["index"] = i
        if results and not BASE_URL:
            BASE_URL = site_base(results[0].get("url"))
        site_adini_tamamla()
        meta = {"base": BASE_URL, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "browser": "Chromium (yeniden üretim)", "count": len(results)}
        _regenerate_reports(results, meta)
        print(f"[✓] Rapor yeniden üretildi ({len(results)} sayfa): {OUT_DIR}/report.html")
        return

    # kaynak dosyayı seç — birden çok konumda ara (data/, ../data/, script yanı)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [".", "data", os.path.join("..", "data"),
                   os.path.join(script_dir, "..", "data"), script_dir]
    candidates = [opts.source] + [
        os.path.join(d, n)
        for d in search_dirs
        for n in (os.path.basename(opts.source), "final_complete_site_map.json",
                  "comprehensive_test_results.json", "all_links_found.json", "site_map.json")
    ]
    source = next((c for c in candidates if os.path.exists(c)), None)
    if not source:
        print(f"[HATA] Link kaynağı bulunamadı: {opts.source}")
        print("       final_complete_site_map.json dosyasını script ile aynı klasöre "
              "veya bir 'data/' klasörüne koy, ya da --source ile tam yolunu ver.")
        sys.exit(1)

    urls = load_urls(source, opts.limit, opts.offset)
    if not BASE_URL and urls:
        BASE_URL = site_base(urls[0])
    site_adini_tamamla()

    # --- BİRİKİMLİ SONUÇ DOSYASI (tüm parçalar buraya yazılır) ---
    # Her sayfa tamamlandıkça results.jsonl'e bir satır eklenir. Böylece:
    #   • parça parça çalıştırma (--offset/--limit) TEK rapora birikir,
    #   • zaten test edilmiş sayfalar atlanır (gerçek devam / resume),
    #   • çökme olsa bile o ana kadarki sonuçlar kaybolmaz.
    jsonl_path = os.path.join(OUT_DIR, "results.jsonl")
    done = set()
    if opts.fresh and os.path.exists(jsonl_path):
        os.remove(jsonl_path)

    if opts.retry_errors and os.path.exists(jsonl_path):
        # Yalnızca HATALI (timeout / yüklenemedi) sayfaları yeniden test et.
        # Sağlam kayıtları koru, hatalıları jsonl'den çıkar ki tekrar denensin.
        keep, retry_urls = [], []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("overall") == "error" or r.get("http_status") in (None, "error"):
                    retry_urls.append(r["url"])
                else:
                    keep.append(r)
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        done = {r["url"] for r in keep}
        todo = list(dict.fromkeys(retry_urls))   # tekilleştir, sırayı koru
        print(f"[*] RETRY-ERRORS: {len(todo)} hatalı sayfa yeniden test edilecek "
              f"(düşük --concurrency önerilir).")
    else:
        if os.path.exists(jsonl_path):
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        done.add(json.loads(line)["url"])
                    except Exception:
                        pass
        todo = [u for u in urls if u not in done]
    total = len(todo)
    print("=" * 74)
    print(f"  {SITE_NAME} — KANITLI EKRAN GÖRÜNTÜSÜ / TEST ARACI")
    print("=" * 74)
    print(f"[*] Kaynak: {source}")
    print(f"[*] Bu aralıkta {len(urls)} sayfa | zaten yapılmış {len(done & set(urls))} | test edilecek {total}")
    print(f"[*] Eşzamanlılık: {opts.concurrency} | Ekran görüntüsü: {opts.screenshots} | Video: {opts.video}")
    if total > 500 and opts.video:
        print("[!] UYARI: video ile çok sayıda sayfa çok yer kaplar. Kritik sayfalar için --video kullan.")
    if total == 0:
        print("[*] Bu aralıktaki tüm sayfalar zaten test edilmiş. Rapor yine de yeniden üretilecek.")

    start = time.time()
    run_results = []
    fout = open(jsonl_path, "a", encoding="utf-8")
    write_lock = asyncio.Lock()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=opts.headed is False)
        version = browser.version
        sem = asyncio.Semaphore(opts.concurrency)

        async def guarded(u, i):
            async with sem:
                rec = await test_page(browser, u, opts, i, total)
                # jsonl'e yazarken büyük link listelerini çıkar (yer kaplamasın)
                slim = {k: v for k, v in rec.items() if k not in ("_collected_links", "_docs")}
                async with write_lock:
                    fout.write(json.dumps(slim, ensure_ascii=False) + "\n")
                    fout.flush()
                return rec

        tasks = [guarded(u, i + 1) for i, u in enumerate(todo)]
        for coro in asyncio.as_completed(tasks):
            run_results.append(await coro)

        broken = []
        if opts.check_links and run_results:
            broken = await check_broken_links(pw.request, run_results, opts.timeout)

        docs_audit = []
        if opts.check_docs and run_results:
            docs_audit = await audit_documents(pw.request, run_results, opts.timeout)

        await browser.close()

    fout.close()
    elapsed = time.time() - start

    # --- Rapor İÇİN: jsonl'deki TÜM geçmişi yükle (bütün parçalar) ---
    results = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except Exception:
                pass
    # görüntü sırası için yeniden numaralandır
    for i, r in enumerate(results, 1):
        r["index"] = i

    # ---- özet ----
    dist = Counter(r["overall"] for r in results)
    status = Counter(r.get("http_status") for r in results)
    tr_pages = sum(1 for r in results if r.get("turkish", {}).get("has_turkish"))
    mojibake = sum(1 for r in results if r.get("turkish", {}).get("mojibake_suspected"))
    no_alt = sum(1 for r in results if r.get("accessibility", {}).get("images_without_alt", 0) > 0)
    missing_h1 = sum(1 for r in results if r.get("accessibility", {}).get("missing_h1"))
    with_js_err = sum(1 for r in results if r.get("js_errors"))
    with_hydration = sum(1 for r in results if r.get("hydration_error"))
    with_res_err = sum(1 for r in results if r.get("resource_errors"))

    summary = f"""{'='*70}
{SITE_NAME} — KANITLI TEST ÖZETİ
{'='*70}
Tarih          : {datetime.now().isoformat()}
Kaynak         : {source}
Bu çalışmada   : {len(run_results)} sayfa test edildi (süre: {elapsed:.0f} sn)
TOPLAM birikmiş: {len(results)} sayfa  (results.jsonl)
Tarayıcı       : Chromium {version}

SONUÇ DAĞILIMI : {dict(dist)}
HTTP DURUM     : {dict(status)}
Türkçe render  : {tr_pages}/{len(results)} sayfada Türkçe karakter, {mojibake} mojibake şüphesi
Alt-text eksik : {no_alt} sayfa
H1 eksik       : {missing_h1} sayfa
Gerçek JS hata : {with_js_err} sayfa  (bunun {with_hydration}'i React hydration hatası #418 vb.)
Kaynak yük.hata: {with_res_err} sayfa  (alt kaynak 404/403 — çoğu sayfanın kendi durumuyla örtüşür)
Kırık link     : {str(len(broken))+' (bu çalışmada)' if opts.check_links else 'kontrol edilmedi (--check-links)'}
Belge/dosya    : {(str(len(docs_audit))+' bulundu; '+str(sum(1 for d in docs_audit if d.get('flag','').startswith(('KIRIK','ULAS','SIZ'))))+' sorunlu -> documents_audit.csv') if opts.check_docs else 'kontrol edilmedi (--check-docs)'}
Görsel/UI kusur: {(str(sum(1 for r in results if (r.get('visual') or {}).get('defect_count')))+' kusurlu sayfa -> gorsel_rapor.html') if opts.check_visual else 'kontrol edilmedi (--check-visual)'}

Kanıtlar       : {OUT_DIR}/screenshots/ (desktop+mobile PNG){' , '+OUT_DIR+'/videos/' if opts.video else ''}
Rapor          : {OUT_DIR}/report.html  (sunum için)
"""
    print("\n" + summary)

    # ---- dosyalar ----
    with open(os.path.join(OUT_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)

    meta = {"base": BASE_URL, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "browser": f"Chromium {version}", "count": len(results)}
    with open(os.path.join(OUT_DIR, "report.html"), "w", encoding="utf-8") as f:
        f.write(build_html_report(results, meta))

    try:
        import pandas as pd
        rows = []
        for r in results:
            a = r.get("accessibility", {})
            rows.append({
                "index": r["index"], "url": r["url"], "overall": r["overall"],
                "http_status": r.get("http_status"), "load_time": r.get("load_time"),
                "turkish_chars": r.get("turkish", {}).get("total", 0),
                "mojibake": r.get("turkish", {}).get("mojibake_suspected"),
                "images_no_alt": a.get("images_without_alt"),
                "missing_h1": a.get("missing_h1"), "title": a.get("title", ""),
                "viewport": r.get("mobile", {}).get("has_viewport_meta"),
                "media_query": r.get("mobile", {}).get("has_media_queries"),
                "forms": r.get("forms", {}).get("forms_found"),
                "sec_missing": ",".join(r.get("security", {}).get("missing", [])),
                "js_errors": len(r.get("js_errors", [])),
                "hydration_error": r.get("hydration_error", False),
                "resource_errors": len(r.get("resource_errors", [])),
                "desktop_shot": r.get("evidence", {}).get("desktop", ""),
                "mobile_shot": r.get("evidence", {}).get("mobile", ""),
            })
        pd.DataFrame(rows).to_excel(os.path.join(OUT_DIR, "report.xlsx"), index=False)
    except Exception as e:
        print(f"[!] Excel yazılamadı ({e}); JSON/HTML hazır.")

    if opts.check_links:
        bl_path = os.path.join(OUT_DIR, "broken_links.csv")
        new_file = not os.path.exists(bl_path)
        with open(bl_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["url", "status", "kaynak_sayfa", "buton_metni"])
            for b in broken:
                w.writerow([b["url"], b["status"], b.get("referrer", ""), b.get("text", "")])

    if opts.check_docs:
        da_path = os.path.join(OUT_DIR, "documents_audit.csv")
        new_file = not os.path.exists(da_path)
        with open(da_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["url", "status", "content_type", "size", "source", "flag",
                            "kaynak_sayfa", "buton_metni"])
            for d in docs_audit:
                w.writerow([d["url"], d.get("status"), d.get("ctype", ""),
                            d.get("size", ""), d.get("source", ""), d.get("flag", ""),
                            d.get("referrer", ""), d.get("text", "")])

    if opts.check_visual:
        vrows = _visual_rows(results)
        with open(os.path.join(OUT_DIR, "gorsel_denetim.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["url", "gorunum", "kusur_turu", "aciklama", "olculen_deger", "css_secici", "metin"])
            for v in vrows:
                w.writerow([v["url"], v["viewport"], v["type"], v["detail"],
                            v["value"], v["selector"], v["text"]])
        with open(os.path.join(OUT_DIR, "gorsel_rapor.html"), "w", encoding="utf-8") as f:
            f.write(build_visual_report(results, meta, cluster=load_cluster_counts(source)))
        vpages = sum(1 for r in results if (r.get("visual") or {}).get("defect_count"))
        print(f"[✓] Görsel denetim: {vpages} kusurlu sayfa, {len(vrows)} kusur "
              f"-> {OUT_DIR}/gorsel_rapor.html , gorsel_denetim.csv")

    print(f"[✓] BİTTİ. Toplam {len(results)} sayfa raporda. Sunum: {OUT_DIR}/report.html")
    print("     Parçalı devam için: --offset <sonraki> --limit <adım>  (aynı klasöre)")
    print("     Bittiğinde bu klasörü (report.html + screenshots/) bana geri gönder.")


def parse_args():
    ap = argparse.ArgumentParser(description="Kanıtlı kapsamlı web sitesi test aracı")
    ap.add_argument("--source", default="final_complete_site_map.json",
                    help="Link kaynağı JSON (varsayılan: final_complete_site_map.json)")
    ap.add_argument("--limit", type=int, default=None, help="Kaç sayfa test edilsin")
    ap.add_argument("--offset", type=int, default=0, help="Kaçıncı sayfadan başlansın (parça parça test için)")
    ap.add_argument("--concurrency", type=int, default=4, help="Eşzamanlı sekme sayısı (varsayılan 4)")
    ap.add_argument("--timeout", type=int, default=30, help="Sayfa başına saniye (varsayılan 30)")
    ap.add_argument("--no-screenshots", dest="screenshots", action="store_false", help="Ekran görüntüsü alma")
    ap.add_argument("--video", action="store_true", help="Her sayfa için video kaydet (yavaş, çok yer)")
    ap.add_argument("--check-links", action="store_true", help="Sayfalardaki linkleri de kontrol et")
    ap.add_argument("--check-docs", action="store_true", help="Belge/dosya (PDF, Word, Excel, ...) linklerini tara ve erişilebilirliğini kontrol et")
    ap.add_argument("--kaydir", action="store_true",
                    help="Ekran görüntüsünden önce sayfayı sona kadar kaydır (lazy görseller ve sayaçlar yüklensin)")
    ap.add_argument("--check-visual", action="store_true", help="Görsel/UI kusur denetimi: içerik taşması (gerçek yatay kayma), kırık görsel, kırpılan metin, boş render (masaüstü+mobil, işaretli kanıt görüntülü)")
    ap.add_argument("--resume", action="store_true", help="Var olan ekran görüntülerini tekrar üretme (varsayılan davranış zaten yapılmış sayfaları atlar)")
    ap.add_argument("--tablet", action="store_true", help="Masaüstü+mobile ek olarak tablet (768×1024) ekran görüntüsü de al")
    ap.add_argument("--fresh", action="store_true", help="results.jsonl'i sıfırla, testi baştan başlat")
    ap.add_argument("--report-only", action="store_true", help="Test çalıştırma; mevcut results.jsonl'den report.html/xlsx/summary'yi yeniden üret (saniyeler)")
    ap.add_argument("--retry-errors", action="store_true", help="Yalnızca hatalı/timeout olmuş sayfaları yeniden test et (düşük --concurrency ile)")
    ap.add_argument("--out-dir", default="test_output", help="Çıktı klasörü (varsayılan: test_output). Link/belge denetimini ayrı klasörde yapmak için değiştir.")
    ap.add_argument("--css", default=None,
                    help="Her sayfaya yüklendikten sonra bu CSS dosyasını ekle (düzeltme önerisini ölçmek için)")
    ap.add_argument("--headed", action="store_true", help="Tarayıcıyı görünür çalıştır (debug)")
    ap.add_argument("--site-adi", default=None, help="Raporlarda görünecek site adı (varsayılan: alan adı)")
    ap.add_argument("--locale", default=None, help=f"Tarayıcı dil/yerel ayarı (varsayılan: {LOCALE})")
    ap.add_argument("--user-agent", default=None, help="Tarayıcının User-Agent değeri")
    ap.set_defaults(screenshots=True)
    return ap.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[!] Kullanıcı durdurdu. Kısmi sonuçlar test_output/ içinde olabilir.")
