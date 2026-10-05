#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 GÖRSEL AI İNCELEME  (visual_ai_review) — YEREL, AÇIK KAYNAK, İNTERNETSİZ
================================================================================
 Amaç: Heuristik (DOM ölçüm) aracın YANINDA ikinci bir kat: her temsilci
       sayfanın ekran görüntüsünü YERELDE çalışan bir görüntü (vision) modeline
       gönderip "insan gözüyle" görsel kusur incelemesi yaptırır. Model taşma,
       üst üste binme, kırık görsel, kırpılan metin, bozuk/boş düzen gibi
       heuristikğin kaçırabileceği şeyleri de yakalar.

 NEDEN YEREL: Ollama ile model senin makinende çalışır -> API/anahtar YOK,
       ücret YOK, veri makineden ÇIKMAZ (gizlilik). Şablon kümelemesi sayesinde
       17k sayfa değil ~temsilciler taranır -> makul süre.

--------------------------------------------------------------------------------
 KURULUM (bir kez):
   1) Ollama'yı kur:  https://ollama.com/download   (Windows/Mac/Linux)
   2) Bir görüntü modeli indir (birini seç):
        ollama pull qwen2.5vl:3b       # önerilen (düzen/OCR iyi, CPU'da makul)
        ollama pull minicpm-v          # daha güçlü OCR, biraz ağır
        ollama pull moondream          # en hızlı, ilk eleme
        ollama pull llama3.2-vision     # GPU varsa daha isabetli
   3) Python bağımlılığı: playwright (zaten kurulu). PIL isteğe bağlı (küçültme):
        pip install pillow

 ÇALIŞTIRMA:
   # önce temsilcileri üret (bir kez):
   python cluster_templates.py
   # sonra AI inceleme:
   python visual_ai_review.py --source template_representatives.json --model qwen2.5vl:3b
   # deneme (ilk 20 temsilci):
   python visual_ai_review.py --limit 20 --model moondream

 ÇIKTILAR (gorsel_ai/ altına):
   gorsel_ai_rapor.html   ŞABLON özetli, görselli AI kusur raporu
   gorsel_ai.csv          url, görünüm, kusur_var, önem, tür, açıklama
   screenshots/           <sayfa>__desktop.png / __mobile.png  (incelenen görüntü)
   results.jsonl          ham AI yanıtları (resume)
================================================================================
"""
import argparse
import asyncio
import base64
import csv
import html
import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tester_v3_evidence import (  # noqa: E402
    load_urls, safe_name, template_signature, load_cluster_counts,
    DESKTOP_VIEWPORT, MOBILE_VIEWPORT, BASE_URL, site_base,
)

SITE_NAME = "MEÜ ÖİDB"
LOCALE = "tr-TR"

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[HATA] Playwright kurulu değil:  pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from PIL import Image  # görüntüyü küçültmek için (isteğe bağlı)
    import io
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False

OUT_DIR = "gorsel_ai"
MAX_W = 1100   # modele göndermeden önce EN GENİŞLİK (genişliğe göre küçült; ezme yok)
MAX_H = 2600   # aşırı uzun tam-sayfa görüntüde üst kısmı al (model okunur kalsın)

PROMPT = (
    "You are a meticulous web QA tester. You are given a {vp} screenshot of a web "
    "page rendered at {w}px wide. Inspect it CAREFULLY for VISUAL layout defects "
    "only (ignore HTTP, speed, wording). Actively look for each of these and decide "
    "if any is present:\n"
    "1. Content overflowing the right edge / cut off / needs horizontal scrolling "
    "(e.g. a long unbroken URL or wide table wider than the screen).\n"
    "2. Elements overlapping, misaligned, or shifted out of place.\n"
    "3. Broken or missing images (empty box, broken-image icon, blank avatar).\n"
    "4. Text that does not fit its box, is clipped or truncated.\n"
    "5. Empty, half-rendered, or broken layout; large meaningless blank area.\n"
    "6. Unreadable contrast (text blending into background).\n"
    "Be strict: if something looks off, report it. Answer with ONLY this JSON "
    "(Turkish text in the string values), nothing else:\n"
    '{{"kusur_var": true/false, "onem": "yuksek|orta|dusuk", '
    '"kusurlar": [{{"tur": "kisa-etiket", "aciklama": "ne ve nerede (Türkçe)"}}], '
    '"ozet": "tek cümle Türkçe"}}\n'
    "If truly nothing is wrong: kusur_var=false and kusurlar=[]."
)


def ollama_tags(base, timeout=5):
    """Ollama açık mı ve hangi modeller var? -> model adları listesi ya da None."""
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/tags", timeout=timeout) as r:
            data = json.loads(r.read())
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return None


def prep_image(png_bytes):
    """Görüntüyü modele hazır hâle getirir: GENİŞLİĞE göre küçültür (aspect korunur,
    ezme YOK), aşırı uzunsa üst kısmı alır. JPEG base64 döner."""
    if _HAVE_PIL:
        try:
            im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            w, h = im.size
            if w > MAX_W:                       # yalnız genişliğe göre küçült
                nh = int(h * MAX_W / w)
                im = im.resize((MAX_W, nh)); w, h = MAX_W, nh
            if h > MAX_H:                       # çok uzunsa üstten kırp (okunur kalsın)
                im = im.crop((0, 0, w, MAX_H))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass
    return base64.b64encode(png_bytes).decode()


def ollama_review(base, model, img_b64, vp, w, timeout):
    """Görüntüyü yerel modele gönderir -> yapılandırılmış kusur sözlüğü."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT.format(vp=vp, w=w), "images": [img_b64]}],
        "stream": False,
        "format": "json",            # Ollama geçerli JSON'a zorlar
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(base.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    content = (data.get("message") or {}).get("content", "") or ""
    try:
        obj = json.loads(content)
    except Exception:
        # bazı modeller JSON'u metne sarabilir -> ilk {...} bloğunu çek
        i, j = content.find("{"), content.rfind("}")
        obj = json.loads(content[i:j + 1]) if 0 <= i < j else {"kusur_var": None, "ozet": content[:200]}
    return {
        "kusur_var": bool(obj.get("kusur_var")),
        "onem": str(obj.get("onem", "") or ""),
        "kusurlar": obj.get("kusurlar", []) if isinstance(obj.get("kusurlar"), list) else [],
        "ozet": str(obj.get("ozet", "") or ""),
    }


async def screenshot(context, url, vp, timeout, full_page=False):
    page = await context.new_page()
    try:
        await page.set_viewport_size(vp)
        await page.goto(url, wait_until="load", timeout=timeout * 1000)
        await page.wait_for_timeout(500)
        # Varsayılan: VIEWPORT görüntü (ekran boyu; model okunur görür, ezilme olmaz).
        # --full-page: tüm sayfa (küçültme üst kısmı alır).
        png = await page.screenshot(full_page=full_page)
        return png
    finally:
        await page.close()


async def run(opts):
    global OUT_DIR, SITE_NAME, LOCALE
    OUT_DIR = opts.out_dir
    SITE_NAME = opts.site_adi or SITE_NAME
    LOCALE = opts.locale or LOCALE
    os.makedirs(os.path.join(OUT_DIR, "screenshots"), exist_ok=True)

    tags = ollama_tags(opts.ollama_url)
    if tags is None:
        print(f"[HATA] Ollama'ya ulaşılamadı ({opts.ollama_url}). Ollama çalışıyor mu?")
        print("       Kur: https://ollama.com/download  ·  sonra:  ollama pull " + opts.model)
        sys.exit(1)
    if opts.model not in tags and opts.model.split(":")[0] not in [t.split(":")[0] for t in tags]:
        print(f"[HATA] '{opts.model}' modeli Ollama'da yok. Mevcut: {tags or '(boş)'}")
        print(f"       İndir:  ollama pull {opts.model}")
        sys.exit(1)
    print(f"[*] Ollama hazır ({opts.ollama_url}) · model: {opts.model}")

    # kaynak URL'ler (varsayılan: temsilciler)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dirs = [".", "data", os.path.join("..", "data"), os.path.join(script_dir, "..", "data"), script_dir]
    src = next((c for c in [opts.source] + [os.path.join(d, os.path.basename(opts.source)) for d in dirs]
                if os.path.exists(c)), None)
    if not src:
        print(f"[HATA] Kaynak bulunamadı: {opts.source}  (önce: python cluster_templates.py)")
        sys.exit(1)
    urls = load_urls(src, opts.limit, opts.offset)
    viewports = [("masaüstü", DESKTOP_VIEWPORT), ("mobil", MOBILE_VIEWPORT)]
    if opts.only == "mobil":
        viewports = [("mobil", MOBILE_VIEWPORT)]
    elif opts.only == "masaustu":
        viewports = [("masaüstü", DESKTOP_VIEWPORT)]

    jsonl = os.path.join(OUT_DIR, "results.jsonl")
    done = set()
    if opts.fresh and os.path.exists(jsonl):
        os.remove(jsonl)
    if os.path.exists(jsonl):
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line); done.add(f"{r['url']}|{r['viewport']}")
                except Exception:
                    pass

    total = len(urls) * len(viewports)
    print(f"[*] Kaynak: {src} · {len(urls)} temsilci × {len(viewports)} görünüm = {total} inceleme")
    print(f"[*] Zaten yapılmış: {len(done)}  ·  Çıktı: {OUT_DIR}/")

    fout = open(jsonl, "a", encoding="utf-8")
    i, flagged = 0, 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True, locale=LOCALE)
        for url in urls:
            name = safe_name(url)
            for vpname, vp in viewports:
                i += 1
                key = f"{url}|{vpname}"
                if key in done:
                    continue
                try:
                    png = await screenshot(context, url, vp, opts.timeout, opts.full_page)
                    shot = os.path.join(OUT_DIR, "screenshots", f"{name}__{vp['width']}.png")
                    with open(shot, "wb") as sf:
                        sf.write(png)
                    verdict = ollama_review(opts.ollama_url, opts.model, prep_image(png),
                                            vpname, vp["width"], opts.timeout)
                    verdict.update({"url": url, "viewport": vpname,
                                    "shot": os.path.relpath(shot, OUT_DIR)})
                except Exception as e:
                    verdict = {"url": url, "viewport": vpname, "kusur_var": None,
                               "onem": "", "kusurlar": [], "ozet": f"hata: {e}", "shot": ""}
                fout.write(json.dumps(verdict, ensure_ascii=False) + "\n"); fout.flush()
                if verdict.get("kusur_var"):
                    flagged += 1
                mark = "KUSUR" if verdict.get("kusur_var") else ("—" if verdict.get("kusur_var") is False else "?")
                print(f"  [{i}/{total}] {mark:5} {vpname:8} {url[:70]}")
        await browser.close()
    fout.close()

    # rapor
    results = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except Exception:
                pass
    counts, vocab = load_cluster_counts(src)
    meta = {"base": site_base(urls[0]) if urls else BASE_URL, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "model": opts.model}
    csv_path = write_csv(results)
    html_path = safe_write(os.path.join(OUT_DIR, "gorsel_ai_rapor.html"),
                           build_ai_report(results, meta, (counts, vocab)))
    fl = sum(1 for r in results if r.get("kusur_var"))
    print(f"\n[✓] BİTTİ. {len(results)} inceleme, {fl} kusurlu görünüm")
    print(f"    Rapor: {html_path}")
    print(f"    CSV  : {csv_path}")
    print(f"    (Veriler {jsonl} içinde de güvende; --fresh olmadan tekrar çalıştırınca "
          f"inceleme atlanır, rapor yeniden üretilir.)")


def safe_write(path, text, newline=None):
    """Dosya kilitliyse (ör. Excel'de açık) alternatif isme yazar; kullanılan yolu döner."""
    try:
        with open(path, "w", newline=newline, encoding="utf-8") as f:
            f.write(text)
        return path
    except PermissionError:
        base, ext = os.path.splitext(path)
        alt = f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
        with open(alt, "w", newline=newline, encoding="utf-8") as f:
            f.write(text)
        print(f"[!] '{path}' yazılamadı (açık/kilitli olabilir). Yerine: {alt}")
        return alt


def write_csv(results):
    import io as _io
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["url", "gorunum", "kusur_var", "onem", "kusur_turu", "aciklama", "ozet"])
    if True:
        for r in results:
            ks = r.get("kusurlar") or []
            if ks:
                for k in ks:
                    w.writerow([r["url"], r["viewport"], r.get("kusur_var"), r.get("onem"),
                                (k or {}).get("tur", ""), (k or {}).get("aciklama", ""), r.get("ozet", "")])
            else:
                w.writerow([r["url"], r["viewport"], r.get("kusur_var"), r.get("onem"),
                            "", "", r.get("ozet", "")])
    return safe_write(os.path.join(OUT_DIR, "gorsel_ai.csv"), buf.getvalue(), newline="")


def build_ai_report(results, meta, cluster):
    counts, vocab = cluster or (None, None)
    have = counts is not None

    def sig_of(u):
        return template_signature(u, vocab) if have else u

    def aff(u):
        return counts.get(sig_of(u), 1) if have else 1

    flagged = [r for r in results if r.get("kusur_var")]
    # şablona göre topla
    rollup = {}
    for r in flagged:
        e = rollup.setdefault(sig_of(r["url"]), {"affected": aff(r["url"]), "n": 0, "ex": r})
        e["n"] += 1
    total_aff = sum(e["affected"] for e in rollup.values())

    def esc(s):
        return html.escape(str(s or ""))

    rrows = ""
    for sig, e in sorted(rollup.items(), key=lambda kv: -kv[1]["affected"]):
        ex = e["ex"]
        th = (f'<a href="{esc(ex.get("shot"))}" target="_blank"><img class="th" src="{esc(ex.get("shot"))}"></a>'
              if ex.get("shot") else "")
        rrows += (f'<tr><td><b>≈{e["affected"]}</b></td><td><code>{esc(sig)}</code></td>'
                  f'<td>{esc(ex.get("ozet"))}</td>'
                  f'<td class="u"><a href="{esc(ex["url"])}" target="_blank">{esc(ex["url"])}</a></td>'
                  f'<td>{th}</td></tr>')

    rows = ""
    for r in sorted(results, key=lambda r: (0 if r.get("kusur_var") else 1)):
        if r.get("kusur_var") is False:
            continue  # raporda yalnız kusurlu/şüpheli görünümler
        ks = "".join(f"<li><b>{esc(k.get('tur'))}</b> — {esc(k.get('aciklama'))}</li>" for k in (r.get("kusurlar") or []))
        badge = ('<span class="b hi">KUSUR</span>' if r.get("kusur_var")
                 else '<span class="b q">belirsiz</span>')
        thumb = (f'<a href="{esc(r.get("shot"))}" target="_blank"><img class="th" src="{esc(r.get("shot"))}"></a>'
                 if r.get("shot") else "")
        aff_html = f' <span class="aff">≈{aff(r["url"])} sayfa</span>' if have else ""
        rows += (f'<tr data-s="{esc(r["url"].lower())}"><td class="u">'
                 f'<a href="{esc(r["url"])}" target="_blank">{esc(r["url"])}</a>{aff_html}'
                 f'<div class="oz">{esc(r.get("ozet"))}</div>'
                 f'{("<ul>"+ks+"</ul>") if ks else ""}</td>'
                 f'<td>{esc(r.get("viewport"))}</td><td>{badge} <span class="on">{esc(r.get("onem"))}</span></td>'
                 f'<td>{thumb}</td></tr>')

    reviewed = len(results)
    return f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<title>{esc(SITE_NAME)} — Görsel AI İnceleme</title><style>
 body{{font-family:system-ui,Arial,sans-serif;margin:0;color:#1f2328;background:#f6f8fa}}
 header{{background:#0b3d66;color:#fff;padding:18px 26px}} header h1{{margin:0;font-size:21px}}
 .meta{{font-size:13px;opacity:.9}} .wrap{{padding:18px 26px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
 .card{{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:12px 16px;min-width:110px}}
 .card b{{font-size:24px;display:block}}
 table{{width:100%;border-collapse:collapse;background:#fff;font-size:13px}}
 th,td{{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}}
 th{{background:#eaeef2;position:sticky;top:0}} .u{{max-width:420px;word-break:break-all}}
 .th{{height:120px;border:1px solid #ccc;border-radius:4px}}
 .b{{padding:1px 7px;border-radius:9px;color:#fff;font-size:11px}} .b.hi{{background:#cf222e}} .b.q{{background:#9a6700}}
 .on{{font-size:11px;color:#57606a}} .oz{{margin:4px 0;color:#333}}
 .aff{{display:inline-block;background:#e7eef6;color:#0b3d66;border:1px solid #c6d6e6;border-radius:9px;padding:1px 7px;font-size:11px}}
 ul{{margin:4px 0 0 16px;padding:0;font-size:12px}} h2{{font-size:17px}}
 code{{background:#f0f0f4;padding:1px 4px;border-radius:4px}}
 input#f{{padding:8px;width:320px;border:1px solid #ccc;border-radius:6px;margin-bottom:10px}}
</style></head><body>
<header><h1>{esc(SITE_NAME)} — Görsel AI İnceleme (yerel model)</h1>
 <div class="meta">Hedef: {esc(meta['base'])} · Tarih: {esc(meta['date'])} · Model: {esc(meta['model'])}
  · İncelenen görünüm: {reviewed} · İnsan-gözü ikinci kat denetim</div></header>
<div class="wrap">
 <div class="cards">
  <div class="card"><b>{reviewed}</b>İncelenen görünüm</div>
  <div class="card" style="color:#cf222e"><b>{len(flagged)}</b>Kusurlu görünüm</div>
  {(f'<div class="card" style="color:#0b3d66"><b>{len(rollup)}</b>Kusurlu düzen</div>'
    f'<div class="card" style="color:#0b3d66"><b>≈{total_aff}</b>Etkilenen sayfa</div>') if have else ''}
 </div>
 <p style="font-size:12px;color:#57606a">Not: Bulgular yerelde çalışan bir görüntü modelinin yorumudur;
 <b>aday</b> niteliğindedir — küçük resimlere bakıp doğrula. Model yanılabilir.</p>
 {(f'<h2>Şablon özeti — tek düzeltme çok sayfa</h2><table><thead><tr><th>≈Etkilenen</th>'
   f'<th>Düzen</th><th>AI özeti</th><th>Örnek</th><th>Görüntü</th></tr></thead><tbody>{rrows}</tbody></table>'
   f'<h2>İnceleme dökümü</h2>') if have and rrows else ''}
 <input id="f" placeholder="URL ara..." oninput="var q=this.value.toLowerCase();document.querySelectorAll('#t tbody tr').forEach(function(r){{r.style.display=r.getAttribute('data-s').indexOf(q)>=0?'':'none'}})">
 <table id="t"><thead><tr><th>URL / AI bulgusu</th><th>Görünüm</th><th>Sonuç</th><th>Görüntü</th></tr></thead>
 <tbody>{rows}</tbody></table>
</div></body></html>"""


def parse_args():
    ap = argparse.ArgumentParser(description="Yerel açık kaynak görüntü modeliyle görsel kusur incelemesi")
    ap.add_argument("--source", default="template_representatives.json",
                    help="URL kaynağı (varsayılan: temsilciler; cluster_templates.py üretir)")
    ap.add_argument("--model", default="qwen2.5vl:3b", help="Ollama görüntü modeli (varsayılan qwen2.5vl:3b)")
    ap.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama sunucu adresi")
    ap.add_argument("--limit", type=int, default=None, help="Kaç temsilci")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--only", choices=["mobil", "masaustu"], default=None, help="Yalnız tek görünüm")
    ap.add_argument("--timeout", type=int, default=120, help="Sayfa/model başına saniye (varsayılan 120)")
    ap.add_argument("--out-dir", default="gorsel_ai")
    ap.add_argument("--full-page", action="store_true",
                    help="Tam sayfa görüntü gönder (varsayılan: viewport/ekran boyu — model için daha okunur)")
    ap.add_argument("--fresh", action="store_true", help="results.jsonl'i sıfırla")
    ap.add_argument("--site-adi", default=None, help="Raporda görünecek site adı")
    ap.add_argument("--locale", default=None, help="Tarayıcı dil/yerel ayarı (ör. en-US)")
    return ap.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[!] Durduruldu. Kısmi sonuçlar gorsel_ai/ içinde.")
