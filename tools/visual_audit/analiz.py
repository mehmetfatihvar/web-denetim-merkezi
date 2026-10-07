#!/usr/bin/env python3
"""
Görsel Denetim - Aşama 2: Temsilci ekran görüntülerini yapay zekaya sorma

tarama.py'nin seçtiği temsilci görüntüleri (ornekler.csv) dilimlere böler,
her dilimi aynı İngilizce prompt ve aynı JSON şemasıyla birden fazla modele sorar,
sonuçları birleştirip modeller arası oylama yapar.

Desteklenen modeller (--modeller, virgülle):
  claude             Anthropic API   (ANTHROPIC_API_KEY)
  gemini             Google Gemini   (GEMINI_API_KEY veya GOOGLE_API_KEY)
  ollama:<model>     Yerel Ollama    (ör. ollama:gemma3:4b)
  openai:<model>     OpenAI uyumlu servis (OPENAI_API_KEY, adres --openai-url):
                     OpenAI, OpenRouter, Groq, LM Studio, vLLM ...

Başka bir site için talimattaki site tanımı ve dil değiştirilebilir:
  --site-tanimi "an e-commerce website" --site-dili German

Kullanım:
  # 1) Önce maliyet/süre tahmini (API çağrısı YAPMAZ)
  python analiz.py --tahmin

  # 2) Deneme turu: 10 sayfa
  python analiz.py --modeller claude,gemini --limit 10

  # 3) Tam tur (yarıda kalırsa aynı komutla devam eder)
  python analiz.py --modeller claude,gemini,ollama:gemma3:4b

  # Ücretsiz Gemini + yerel gemma hepsine, Claude yalnızca hakem:
  python analiz.py --modeller gemini,ollama:gemma3:4b --dakika-limit 8
  python analiz.py --hakem claude --tahmin      # hakeme kaç dilim gidecek, maliyet
  python analiz.py --hakem claude

  # Claude'u toplu istekle (Batch API, %50 ucuz) çalıştırmak: --toplu ekleyin
  python analiz.py --hakem claude --toplu

  # Yeniden çekilmiş (--kaydir) görüntülerle çalışmak:
  python analiz.py --modeller gemini --klasor ..\\yeniden_cekim\\screenshots

  # Model sürümü seçmek: claude:claude-sonnet-5, gemini:<model adı>

  # Gemini'de kullanılabilir modelleri listele
  python analiz.py --gemini-listele

Çıktılar (--cikti, varsayılan: denetim_cikti/ai):
  sonuclar.jsonl  - her (model, görüntü, dilim) için ham cevap (önbellek)
  bulgular.csv    - her bulgu bir satır
  oylama.csv      - aynı dilimde aynı türde hata bulan model sayısı
  ozet.txt        - model başına bulgu sayısı, token kullanımı, tahmini maliyet

Bağımlılıklar: pip install pillow anthropic google-genai ollama
"""

import argparse
import csv
import io
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# ------------------------------------------------------------------ AYARLAR

DILIM = {                     # cihaz -> (hedef genişlik, dilim yüksekliği)
    "desktop": (1024, 1024),
    "mobile": (375, 1334),    # yaklaşık 2 telefon ekranı
}
VARSAYILAN_DILIM = (1024, 1024)

CLAUDE_MODEL = "claude-opus-5"
ZAMAN_ASIMI = 300       # sn; cevapsız kalan bağlantı asılı kalmasın, hata sayılıp yeniden denensin
DENEME = 6               # geçici hatalarda (503 yoğunluk, 429 dakikalık sınır) toplam deneme
GEMINI_MODEL = "gemini-3.6-flash"   # --gemini-dene ile ücretsiz sürümde çalıştığı doğrulandı

# $ / 1M token (girdi, çıktı) - yalnızca tahmin içindir, güncel fiyatı kontrol edin
CLAUDE_FIYAT = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

HATA_TURLERI = [
    "horizontal_overflow", "overlap", "cut_off_text", "broken_image", "misalignment",
    "low_contrast", "mojibake", "empty_gap", "broken_navigation", "missing_data", "other",
]

SEMA = {
    "type": "object",
    "properties": {
        "visible_text_sample": {"type": "string"},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": HATA_TURLERI},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "location": {"type": "string"},
                    "evidence_text": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["type", "severity", "confidence", "location",
                             "evidence_text", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["visible_text_sample", "defects"],
    "additionalProperties": False,
}

SITE_TANIMI = "a Turkish university website (Mersin Üniversitesi)"
SITE_DILI = "Turkish"

TALIMAT_SABLONU = """You are a meticulous UI QA reviewer for {site}.
You receive ONE horizontal slice of a full-page screenshot. Report only VISUAL defects a real visitor would notice.

Defect types: horizontal_overflow (content wider than the screen, cut at the left or right edge),
overlap (elements covering each other unintentionally), cut_off_text, broken_image (missing, broken icon,
empty frame), misalignment, low_contrast (text hard to read), mojibake (garbled characters such as
'Ã¼', 'ÅŸ', 'Ä±' instead of {dil} letters), empty_gap (large unexplained empty area), broken_navigation,
missing_data (statistics or fields showing 0, '#0', 'null', 'undefined', placeholder text), other.

Rules:
- Evidence first. For every defect copy the visible text next to it exactly into evidence_text
  (or describe the element if there is no text). Never invent text.
- NOT defects: intentional design such as hero banners with text on photos, floating or sticky buttons
  (accessibility, scroll-to-top, chat), carousel items partially visible when the carousel has arrows
  or dots, decorative overlaps.
- The slice is cut at its top and bottom edges on purpose. Content cut at the TOP or BOTTOM edge of
  the slice is NOT a defect. Content cut at the LEFT or RIGHT edge IS relevant.
- {dil} text is expected and correct.
- If you are not sure, leave it out. An empty defects list is a perfectly good answer.
- visible_text_sample: copy one short piece of text you can read in the slice, exactly as written.
  It is used to verify that you actually read the image."""

TALIMAT = TALIMAT_SABLONU.format(site=SITE_TANIMI, dil=SITE_DILI)


VIEWPORT = {"desktop": 1366, "mobile": 375}   # ekran görüntülerinin çekildiği genişlik


def baglam_metni(cihaz, genislik, dilim_no, dilim_sayisi, y0, y1):
    vp = VIEWPORT.get(cihaz, genislik)
    metin = f"Device: {cihaz} (viewport {vp} px wide). "
    if genislik > vp:
        metin += (f"The page rendered {genislik} px wide, i.e. wider than the screen; this "
                  "overflow is already known, so look for its visible effects and other defects. ")
    return metin + f"Slice {dilim_no} of {dilim_sayisi}, page pixels {y0}-{y1} from the top."


# ------------------------------------------------------------------ DİLİMLEME

def dilim_secimi(toplam, max_dilim):
    """Uzun sayfalarda ilk (max_dilim-1) dilim + son dilim (footer) seçilir."""
    if toplam <= max_dilim:
        return list(range(toplam))
    if max_dilim == 1:
        return [0]
    return list(range(max_dilim - 1)) + [toplam - 1]


def dilimle(yol, cihaz, max_dilim, secili=None):
    """Görüntüyü hedef genişliğe küçültür ve dilimler; uzun sayfalarda son dilim (footer)
    de alınır. PNG baytları döner."""
    hedef_w, dilim_h = DILIM.get(cihaz, VARSAYILAN_DILIM)
    with Image.open(yol) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w > hedef_w:
            im = im.resize((hedef_w, round(h * hedef_w / w)), Image.LANCZOS)
        W, H = im.size
        oran = w / W
        toplam = max(1, -(-H // dilim_h))
        dilimler = []
        # secili verilirse (hakem modu) seçim kuralından bağımsız olarak o dilimler üretilir
        sira = (sorted(n - 1 for n in secili if 0 < n <= toplam) if secili is not None
                else dilim_secimi(toplam, max_dilim))
        for i in sira:
            y0, y1 = i * dilim_h, min(H, (i + 1) * dilim_h)
            buf = io.BytesIO()
            im.crop((0, y0, W, y1)).save(buf, "PNG", optimize=True)
            dilimler.append({"no": i + 1, "toplam": toplam, "png": buf.getvalue(),
                             "y0": round(y0 * oran), "y1": round(y1 * oran),
                             "w": W, "h": y1 - y0})
        return w, dilimler


# ------------------------------------------------------------------ MODEL İSTEMCİLERİ

class HizSiniri:
    """Dakikada en fazla N istek (ücretsiz kotalara takılmamak için). 0 = sınırsız."""
    def __init__(self, dakikada):
        self.aralik = 60.0 / dakikada if dakikada else 0.0
        self.kilit = threading.Lock()
        self.sonraki = 0.0

    def bekle(self):
        if not self.aralik:
            return
        with self.kilit:
            simdi = time.monotonic()
            bekleme = max(0.0, self.sonraki - simdi)
            self.sonraki = max(simdi, self.sonraki) + self.aralik
        if bekleme:
            time.sleep(bekleme)


class Claude:
    kapali = False

    def __init__(self, model, effort):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=6)
        self.ad, self.model, self.effort = f"claude:{model}", model, effort

    def parametreler(self, png, baglam):
        """Normal ve toplu (Batch) isteklerin ortak parametreleri."""
        import base64
        output_config = {"format": {"type": "json_schema", "schema": SEMA}}
        if self.effort:
            output_config["effort"] = self.effort
        return {
            "model": self.model,
            "max_tokens": 16000,
            "system": TALIMAT,
            "output_config": output_config,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(png).decode()}},
                {"type": "text", "text": baglam},
            ]}],
        }

    @staticmethod
    def cevap_coz(r):
        kullanim = {"girdi": r.usage.input_tokens, "cikti": r.usage.output_tokens}
        if r.stop_reason == "refusal":
            return None, kullanim, "refusal"
        if r.stop_reason == "max_tokens":
            return None, kullanim, "max_tokens"
        metin = next(b.text for b in r.content if b.type == "text")
        return json.loads(metin), kullanim, ""

    def sor(self, png, baglam):
        r = self.client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",          # güvenlik sınıflandırıcısı reddederse önerilen modele düş
            **self.parametreler(png, baglam),
        )
        return self.cevap_coz(r)

    def hata_tekrar_denenir_mi(self, e):
        return isinstance(e, (self.anthropic.RateLimitError, self.anthropic.APIConnectionError,
                              self.anthropic.InternalServerError))


def json_ayikla(metin):
    """Model cevabından JSON nesnesini çıkarır (```json çitleri / önce-sonra metin olabilir)
    ve şemanın temel alanlarını doğrular."""
    s = metin.strip()
    bas, son = s.find("{"), s.rfind("}")
    if bas < 0 or son <= bas:
        raise ValueError("JSON nesnesi yok")
    try:
        veri = json.loads(s[bas:son + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"geçersiz JSON ({e.msg})")
    if not isinstance(veri, dict) or not isinstance(veri.get("defects"), list):
        raise ValueError("'defects' listesi yok")
    temiz = []
    for d in veri["defects"]:
        if not isinstance(d, dict):
            continue
        d.setdefault("type", "other")
        if d["type"] not in HATA_TURLERI:
            d["type"] = "other"
        for alan in ("severity", "confidence"):
            if d.get(alan) not in ("low", "medium", "high"):
                d[alan] = "low"
        for alan in ("location", "evidence_text", "description"):
            d[alan] = str(d.get(alan, ""))
        temiz.append(d)
    veri["defects"] = temiz
    veri["visible_text_sample"] = str(veri.get("visible_text_sample", ""))
    return veri


class Gemini:
    kapali = False

    def __init__(self, model):
        from google import genai
        from google.genai import types
        self.types = types
        try:   # GEMINI_API_KEY / GOOGLE_API_KEY; zaman aşımı milisaniye
            self.client = genai.Client(
                http_options=types.HttpOptions(timeout=ZAMAN_ASIMI * 1000))
        except Exception:   # zaman aşımını desteklemeyen eski kütüphane sürümü
            self.client = genai.Client()
        self.ad, self.model = f"gemini:{model}", model
        # Gemma modelleri Gemini API'de sistem talimatı ve JSON şemasını desteklemeyebilir:
        # talimat + şema mesajın içine konur, JSON cevaptan ayıklanır.
        self.gemma = model.startswith("gemma")

    def sor(self, png, baglam):
        t = self.types
        gorsel = t.Part.from_bytes(data=png, mime_type="image/png")
        afc = t.AutomaticFunctionCallingConfig(disable=True)
        if self.gemma:
            metin = (f"{TALIMAT}\n\nReturn ONLY one JSON object (no markdown, no extra text) "
                     f"that matches this JSON schema:\n{json.dumps(SEMA)}\n\n{baglam}")
            config = t.GenerateContentConfig(temperature=0, automatic_function_calling=afc)
            try:
                r = self.client.models.generate_content(model=self.model,
                                                        contents=[gorsel, metin], config=config)
            except Exception as e:
                if "500" not in str(e):
                    raise
                # Gemma bazı PNG'lerde kalıcı 500 veriyor: bir kez JPEG ile dene, olmazsa
                # uzun beklemelerle kanalı meşgul etmeden bırak (hakem bakar)
                buf = io.BytesIO()
                Image.open(io.BytesIO(png)).convert("RGB").save(buf, "JPEG", quality=90)
                jpeg = t.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
                try:
                    r = self.client.models.generate_content(model=self.model,
                                                            contents=[jpeg, metin], config=config)
                except Exception as e2:
                    if "500" not in str(e2):
                        raise   # 429/503 gibi geçici hatalar normal tekrar denemeye kalsın
                    raise RuntimeError(f"gemma_500_kalici (PNG ve JPEG): {str(e2)[:150]}")
        else:
            config = t.GenerateContentConfig(
                system_instruction=TALIMAT,
                response_mime_type="application/json",
                response_json_schema=SEMA,
                temperature=0,
                automatic_function_calling=afc,
            )
            r = self.client.models.generate_content(model=self.model, contents=[gorsel, baglam],
                                                    config=config)
        u = r.usage_metadata
        kullanim = {"girdi": getattr(u, "prompt_token_count", 0) or 0,
                    "cikti": getattr(u, "candidates_token_count", 0) or 0}
        if not r.text:
            return None, kullanim, "bos_cevap"
        try:
            return json_ayikla(r.text), kullanim, ""
        except ValueError as e:
            return None, kullanim, f"json_hatasi: {e}: {r.text[:150]!r}"

    def hata_tekrar_denenir_mi(self, e):
        metin = str(e)
        if "gemma_500_kalici" in metin:
            return False
        if "NOT_FOUND" in metin or "'code': 404" in metin:
            if not self.kapali:
                print(f"\n⛔ {self.ad}: model bu hesapta kullanılamıyor (404). "
                      "`python analiz.py --gemini-dene` ile çalışan modeli bulun.\n", flush=True)
            self.kapali = True
            return False
        if "PerDay" in metin or "per day" in metin.lower():
            # Günlük ücretsiz kota bitti: bu çalıştırmada Gemini'yi durdur, yarın devam edilir
            if not self.kapali:
                print(f"\n⛔ {self.ad}: günlük kota doldu. Kalan istekler atlanıyor; "
                      "yarın aynı komutla kaldığı yerden devam edin.\n", flush=True)
            self.kapali = True
            return False
        return (any(k in metin for k in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500"))
                or zaman_asimi_mi(e))


class Ollama:
    kapali = False

    def __init__(self, model):
        import ollama
        self.client = ollama.Client()
        self.ad, self.model = f"ollama:{model}", model

    def sor(self, png, baglam):
        r = self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": TALIMAT},
                      {"role": "user", "content": baglam, "images": [png]}],
            format=SEMA,
            options={"num_ctx": 4096, "temperature": 0},
        )
        kullanim = {"girdi": r.get("prompt_eval_count", 0) or 0,
                    "cikti": r.get("eval_count", 0) or 0}
        return json.loads(r["message"]["content"]), kullanim, ""

    def hata_tekrar_denenir_mi(self, e):
        return False


class OpenAIUyumlu:
    """OpenAI Chat Completions biçimini konuşan her servis: OpenAI, OpenRouter, Groq,
    Mistral, Together, LM Studio, vLLM, llama.cpp sunucusu... Ek paket gerektirmez.
    Sağlayıcıların JSON şeması desteği farklı olduğundan şema talimata yazılır ve
    JSON cevaptan ayıklanır (Gemma ile aynı yol)."""
    kapali = False

    def __init__(self, model, url, anahtar):
        if not model:
            sys.exit("openai:<model> biçiminde model adı verin (ör. openai:gpt-5-mini)")
        self.ad, self.model = f"openai:{model}", model
        self.url = url.rstrip("/") + "/chat/completions"
        self.anahtar = anahtar

    def sor(self, png, baglam):
        import base64
        import urllib.request
        metin = (f"Return ONLY one JSON object (no markdown, no extra text) that matches this "
                 f"JSON schema:\n{json.dumps(SEMA)}\n\n{baglam}")
        govde = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": TALIMAT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(png).decode()}},
                    {"type": "text", "text": metin},
                ]},
            ],
        }
        basliklar = {"Content-Type": "application/json"}
        if self.anahtar:
            basliklar["Authorization"] = f"Bearer {self.anahtar}"
        istek = urllib.request.Request(self.url, data=json.dumps(govde).encode(),
                                       headers=basliklar, method="POST")
        try:
            with urllib.request.urlopen(istek, timeout=300) as y:
                r = json.loads(y.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        u = r.get("usage") or {}
        kullanim = {"girdi": u.get("prompt_tokens", 0) or 0,
                    "cikti": u.get("completion_tokens", 0) or 0}
        secim = (r.get("choices") or [{}])[0]
        icerik = (secim.get("message") or {}).get("content") or ""
        if isinstance(icerik, list):   # bazı sağlayıcılar parça listesi döner
            icerik = "".join(p.get("text", "") for p in icerik if isinstance(p, dict))
        if not icerik:
            return None, kullanim, "bos_cevap"
        try:
            return json_ayikla(icerik), kullanim, ""
        except ValueError as e:
            return None, kullanim, f"json_hatasi: {e}: {icerik[:150]!r}"

    def hata_tekrar_denenir_mi(self, e):
        metin = str(e)
        if "HTTP 404" in metin or "HTTP 401" in metin or "HTTP 403" in metin:
            if not self.kapali:
                print(f"\n⛔ {self.ad}: {metin[:200]}\n", flush=True)
            self.kapali = True
            return False
        return any(k in metin for k in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503",
                                        "timed out", "Connection"))


def istemci_olustur(ad, a):
    """'claude', 'claude:<model>', 'gemini', 'gemini:<model>', 'ollama:<model>',
    'openai:<model>' (OpenAI uyumlu herhangi bir servis, --openai-url ile)"""
    tur, _, model = ad.partition(":")
    if tur == "claude":
        ist = Claude(model or a.claude_model, a.claude_effort)
    elif tur == "gemini":
        ist = Gemini(model or a.gemini_model)
    elif tur == "ollama" and model:
        return Ollama(model)
    elif tur == "openai":
        ist = OpenAIUyumlu(model, a.openai_url, os.environ.get("OPENAI_API_KEY", ""))
    else:
        sys.exit(f"Bilinmeyen model: {ad}")
    ist.sinir = HizSiniri(a.dakika_limit)
    return ist


# ------------------------------------------------------------------ ÇALIŞTIRMA

def http_hatalilari_ayikla(satirlar, results_yol):
    """Tester'ın results.jsonl'ine göre HTTP 200 dönmeyen sayfaları (404/403 hata sayfası
    görüntüleri) AI analizinden çıkarır; listesini http_hatali.csv'ye yazar."""
    if not results_yol.exists():
        return satirlar
    from temsilci_urls import safe_name
    durum = {}
    with open(results_yol, encoding="utf-8") as f:
        for satir in f:
            try:
                r = json.loads(satir)
            except json.JSONDecodeError:
                continue
            if r.get("url"):
                durum[safe_name(r["url"])] = (r.get("http_status"), r["url"])
    hatali = {ad: d for ad, d in durum.items() if d[0] != 200}
    if not hatali:
        return satirlar
    kalan = [r for r in satirlar if r["sayfa"] not in hatali]
    yol = results_yol.parent / "http_hatali.csv"
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["http_durum", "url", "sayfa"])
        for ad, (kod, url) in sorted(hatali.items(), key=lambda x: (str(x[1][0]), x[1][1])):
            w.writerow([kod, url, ad])
    print(f"🚫 HTTP 200 dönmeyen {len(hatali)} sayfa AI analizinden çıkarıldı "
          f"({len(satirlar) - len(kalan)} görüntü) -> {yol}")
    return kalan


def ornekleri_oku(yol, limit, klasor=None):
    with open(yol, encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.DictReader(f, delimiter=";"))
    if klasor:   # yeniden çekilmiş görüntüler: aynı dosya adları, farklı klasör
        k = Path(klasor)
        for r in satirlar:
            r["tam_yol"] = str(k / Path(r["dosya"]).name)
        eksik = [r for r in satirlar if not Path(r["tam_yol"]).exists()]
        if eksik:
            print(f"⚠️  {len(eksik)} görüntü {k} içinde yok, atlanıyor "
                  f"(ör. {Path(eksik[0]['dosya']).name})")
        satirlar = [r for r in satirlar if Path(r["tam_yol"]).exists()]
        satirlar = http_hatalilari_ayikla(satirlar, k.parent / "results.jsonl")
    if limit:
        sayfalar = list(dict.fromkeys(r["sayfa"] for r in satirlar))[:limit]
        secili = set(sayfalar)
        satirlar = [r for r in satirlar if r["sayfa"] in secili]
    return satirlar


def onbellegi_oku(yol):
    bitti = set()
    if yol.exists():
        with open(yol, encoding="utf-8") as f:
            for satir in f:
                try:
                    r = json.loads(satir)
                except json.JSONDecodeError:
                    continue
                if not r.get("hata"):
                    bitti.add((r["model"], r["dosya"], r["dilim"]))
    return bitti


def kisa_hata(hata):
    """Ekran için kısa hata metni; kota hatalarında hangi sınırın aşıldığını öne çıkarır."""
    import re
    ayrinti = re.findall(r"(quotaMetric|quotaId|quotaValue)'?\"?: ?'?\"?([\w/.-]+)", hata)
    ek = " | " + ", ".join(f"{k}={v}" for k, v in ayrinti) if ayrinti else ""
    return hata[:150] + ek


def zaman_asimi_mi(e):
    metin = f"{type(e).__name__} {e}".lower()
    return "timeout" in metin or "timed out" in metin


def tek_istek(istemci, is_):
    for deneme in range(DENEME):
        if getattr(istemci, "kapali", False):
            return None, {"girdi": 0, "cikti": 0}, "kota_bitti", 0
        if getattr(istemci, "sinir", None):
            istemci.sinir.bekle()
        try:
            baslangic = time.time()
            cevap, kullanim, hata = istemci.sor(is_["png"], is_["baglam"])
            return cevap, kullanim, hata, round(time.time() - baslangic, 1)
        except Exception as e:
            if deneme < DENEME - 1 and istemci.hata_tekrar_denenir_mi(e):
                time.sleep(min(15 * (deneme + 1), 60))   # 15, 30, 45, 60, 60 sn
                continue
            return None, {"girdi": 0, "cikti": 0}, f"{type(e).__name__}: {str(e)[:2000]}", 0


def hakem_dilimleri(cikti, hakem_ad, ornek=0, grup="sablon", sadece_bakilamayan=False):
    """Hakeme gidecek dilimler: bir hata türünü 2'den az model bulduysa (anlaşmazlık ya da
    tek oy), herhangi bir model 'high' önem verdiyse veya ana model dilime hiç bakamadıysa.
    ornek > 0 ise her gruptan en fazla `ornek` dilim seçilir:
      grup="sablon": (şablon, cihaz, hata türü) - aynı şablondaki aynı hata aynı sebepten
      grup="tur":    (cihaz, hata türü), RASTGELE örnek - hata türü başına isabet oranı ölçümü
    sadece_bakilamayan: yalnızca ana modelin hiç bakamadığı dilimler (ör. ayrı kotalı model ile)."""
    yol = cikti / "sonuclar.jsonl"
    if not yol.exists():
        sys.exit(f"Önce hakem dışındaki modelleri çalıştırın: {yol} yok")
    bakan = defaultdict(set)
    bulan = defaultdict(set)
    yuksek = defaultdict(set)   # dilim -> 'high' verilen türler
    kalici_hata = set()         # ana modelin hiç bakamadığı dilimler (ör. Gemma kalıcı 500)
    grup_bilgisi = {}           # dilim -> (şablon, cihaz)
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            try:
                r = json.loads(satir)
            except json.JSONDecodeError:
                continue
            if r["model"] == hakem_ad:
                continue
            k = (r["dosya"], r["dilim"])
            grup_bilgisi[k] = (r.get("sablon", ""), r.get("cihaz", ""))
            if r["hata"]:
                if "kalici" in r["hata"]:
                    kalici_hata.add(k)
                continue
            bakan[k].add(r["model"])
            for d in (r["cevap"] or {}).get("defects", []):
                bulan[(k, d.get("type"))].add(r["model"])
                if d.get("severity") == "high":
                    yuksek[k].add(d.get("type"))

    def anahtar(k, tur):
        sablon, cihaz = grup_bilgisi[k]
        return (cihaz, tur) if grup == "tur" else (sablon, cihaz, tur)

    adaylar = defaultdict(set)
    if not sadece_bakilamayan:
        for k, turler in yuksek.items():
            for tur in turler:
                adaylar[anahtar(k, tur)].add(k)
        for (k, tur), modeller in bulan.items():
            if len(modeller) < 2:
                adaylar[anahtar(k, tur)].add(k)
    for k in kalici_hata - set(bakan):
        if sadece_bakilamayan:
            adaylar[("_bakilamadi",)].add(k)
        elif grup != "tur":      # tür örneklemesinde bakılamayanlar ayrı bir turda ele alınır
            adaylar[anahtar(k, "_bakilamadi")].add(k)

    if ornek <= 0 or sadece_bakilamayan:
        return set().union(*adaylar.values()) if adaylar else set()
    import random
    rastgele = random.Random(42)   # tekrarlanabilir örneklem
    sec = set()
    for g, dilimler in sorted(adaylar.items()):
        dilimler = sorted(dilimler)
        sec.update(rastgele.sample(dilimler, ornek) if (grup == "tur" and len(dilimler) > ornek)
                   else dilimler[:ornek])
    toplam = len(set().union(*adaylar.values()))
    print(f"   örnekleme ({grup}): {len(adaylar)} grup, grup başına en fazla "
          f"{ornek} -> {len(sec)}/{toplam} dilim")
    return sec


def calistir(a, ornekler, cikti, istemciler, filtre=None):
    onbellek_yol = cikti / "sonuclar.jsonl"
    bitti = onbellegi_oku(onbellek_yol)
    kilit = threading.Lock()

    isler = []
    print(f"✂️  {len(ornekler)} görüntü dilimleniyor (görüntü başına en fazla {a.dilim} dilim)...")
    for o in ornekler:
        try:
            secili = ({n for (dosya, n) in filtre if dosya == o["dosya"]}
                      if filtre is not None else None)
            if secili is not None and not secili:
                continue
            genislik, dilimler = dilimle(o["tam_yol"], o["cihaz"], a.dilim, secili)
        except Exception as e:
            print(f"  ⚠️  açılamadı: {o['dosya']} ({e})")
            continue
        for d in dilimler:
            if filtre is not None and (o["dosya"], d["no"]) not in filtre:
                continue
            baglam =baglam_metni(o["cihaz"], genislik, d["no"], d["toplam"], d["y0"], d["y1"])
            for ist in istemciler:
                if (ist.ad, o["dosya"], d["no"]) not in bitti:
                    isler.append({"istemci": ist, "o": o, "d": d, "png": d["png"],
                                  "baglam": baglam})
    print(f"🧮 {len(isler)} istek yapılacak ({len(bitti)} tanesi önceden tamamlanmış)")

    if a.toplu:   # Claude istekleri Batch API ile (%50 ucuz, sonuçlar genelde 1 saat içinde)
        for ist in istemciler:
            if isinstance(ist, Claude):
                toplu_calistir(ist, [i for i in isler if i["istemci"] is ist], cikti)
        isler = [i for i in isler if not isinstance(i["istemci"], Claude)]
    if not isler:
        return

    paralel ={ist.ad: (1 if ist.ad.startswith("ollama:") else a.paralel) for ist in istemciler}
    havuzlar = {ad: ThreadPoolExecutor(max_workers=n) for ad, n in paralel.items()}
    baslangic = time.time()
    yapilamayan = Counter()
    basarili = 0
    with open(onbellek_yol, "a", encoding="utf-8") as f:
        gelecekler = {havuzlar[is_["istemci"].ad].submit(tek_istek, is_["istemci"], is_): is_
                      for is_ in isler}
        for i, g in enumerate(as_completed(gelecekler), 1):
            is_ = gelecekler[g]
            cevap, kullanim, hata, sure = g.result()
            o, d = is_["o"], is_["d"]
            kayit = {"model": is_["istemci"].ad, "dosya": o["dosya"], "sayfa": o["sayfa"],
                     "cihaz": o["cihaz"], "sablon": o["sablon"], "dilim": d["no"],
                     "dilim_toplam": d["toplam"], "y0": d["y0"], "y1": d["y1"],
                     "cevap": cevap, "kullanim": kullanim, "hata": hata, "sure": sure}
            with kilit:
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
                f.flush()
            if hata:
                yapilamayan[hata_turu(hata)] += 1
            else:
                basarili += 1
            if hata and hata != "kota_bitti":
                print(f"  ❌ {kayit['model']} {o['dosya'][:60]} #{d['no']}: {kisa_hata(hata)}")
            if i % 20 == 0 or i == len(isler) or len(isler) <= 20:
                gecen = time.time() - baslangic
                print(f"  [{i}/{len(isler)}] ✓ {basarili} başarılı  ✗ {i - basarili} yapılamadı  "
                      f"~{gecen / i * (len(isler) - i) / 60:.0f} dk kaldı",
                      flush=True)
    for h in havuzlar.values():
        h.shutdown()
    yapilamayan_ozeti(yapilamayan, len(isler), hakem=filtre is not None)


def hata_turu(hata):
    if "gemma_500_kalici" in hata:
        return "Gemma kalıcı 500 (PNG ve JPEG denendi)"
    if hata == "kota_bitti" or "429" in hata or "RESOURCE_EXHAUSTED" in hata:
        return "kota / hız sınırı"
    if "json" in hata or hata == "bos_cevap":
        return "geçersiz ya da boş cevap"
    if "timeout" in hata.lower() or "timed out" in hata.lower():
        return "zaman aşımı (cevap gelmedi)"
    return "bağlantı / sunucu hatası"


def yapilamayan_ozeti(sayac, toplam, hakem=False):
    """Çalışma sonunda kaç isteğin yapılamadığını ve ne yapılacağını açıkça yazar."""
    n = sum(sayac.values())
    if not n:
        print(f"\n✅ {toplam} isteğin hepsi tamamlandı.")
        return
    ayrinti = ", ".join(f"{a}: {s}" for a, s in sayac.most_common())
    if hakem:
        print(f"\n⚠ Hakem: {toplam} istekten {n} tanesi yapılamadı ({ayrinti}).\n"
              "   NE YAPMALI: Aynı adımı (3c. Hakem modeli) tekrar çalıştırın; yalnız yapılamayanlar\n"
              "   yeniden denenir. Ardından 4, 5 ve 6. adımları yeniden çalıştırın.", flush=True)
        return
    print(f"\n⚠ {toplam} istekten {n} tanesi yapılamadı ({ayrinti}).\n"
          "   NE YAPMALI: Aynı adımı (3b. Yapay zekâ analizi) tekrar çalıştırın; yalnız yapılamayanlar\n"
          "   yeniden denenir, tamamlananlar atlanır. Kota hatasıysa sınır sıfırlanınca (çoğu zaman\n"
          "   ertesi gün) çalıştırın. Ardından 3c. Hakem modeli ve sonraki adımları (4, 5, 6) da\n"
          "   yeniden çalıştırın ki sonuçlar güncellensin.\n"
          "   Gemma bazı görüntülerde 500'ü kalıcı verir; tekrar denemede yine düşenlere hakem\n"
          "   model bakar (3c), yani bu dilimler denetimsiz kalmaz.", flush=True)


# ------------------------------------------------------------------ TOPLU İSTEK (BATCH)

TOPLU_MAX_BAYT = 150 * 1024 * 1024   # Batch sınırı 256 MB; güvenli pay bırakılır
TOPLU_MAX_ISTEK = 10000


def kayit_olustur(model, meta, cevap, kullanim, hata, sure, toplu=False):
    return {"model": model, "dosya": meta["dosya"], "sayfa": meta["sayfa"],
            "cihaz": meta["cihaz"], "sablon": meta["sablon"], "dilim": meta["dilim"],
            "dilim_toplam": meta["dilim_toplam"], "y0": meta["y0"], "y1": meta["y1"],
            "cevap": cevap, "kullanim": kullanim, "hata": hata, "sure": sure, "toplu": toplu}


def toplu_calistir(ist, isler, cikti):
    """Claude isteklerini Message Batches API ile gönderir. Gönderilen batch'ler
    toplu_durum.json'a yazılır; Ctrl+C ile çıkılırsa aynı komut beklemeye devam eder."""
    import uuid
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    durum_yol = cikti / "toplu_durum.json"
    durum = json.loads(durum_yol.read_text(encoding="utf-8")) if durum_yol.exists() else []

    def kaydet():
        durum_yol.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")

    # Bekleyen batch'lerde zaten olan dilimleri tekrar gönderme
    bekleyen = {(m["dosya"], m["dilim"]) for b in durum
                if b["model"] == ist.ad and not b.get("toplandi") for m in b["istekler"].values()}
    isler = [i for i in isler if (i["o"]["dosya"], i["d"]["no"]) not in bekleyen]

    # Yeni batch'leri boyut sınırına göre parçalayıp gönder
    parca, meta, boyut = [], {}, 0
    def gonder():
        nonlocal parca, meta, boyut
        if not parca:
            return
        b = ist.client.messages.batches.create(requests=parca)
        durum.append({"id": b.id, "model": ist.ad, "istekler": meta,
                      "olusturma": time.strftime("%Y-%m-%d %H:%M")})
        kaydet()
        print(f"📦 Batch gönderildi: {b.id} ({len(parca)} istek)")
        parca, meta, boyut = [], {}, 0

    onek = uuid.uuid4().hex[:8]
    for n, is_ in enumerate(isler):
        o, d = is_["o"], is_["d"]
        cid = f"{onek}-{n}"
        params = ist.parametreler(is_["png"], is_["baglam"])
        istek_boyut = len(params["messages"][0]["content"][0]["source"]["data"]) + 20000
        if parca and (boyut + istek_boyut > TOPLU_MAX_BAYT or len(parca) >= TOPLU_MAX_ISTEK):
            gonder()
        parca.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(**params)))
        meta[cid] = {"dosya": o["dosya"], "sayfa": o["sayfa"], "cihaz": o["cihaz"],
                     "sablon": o["sablon"], "dilim": d["no"], "dilim_toplam": d["toplam"],
                     "y0": d["y0"], "y1": d["y1"]}
        boyut += istek_boyut
    gonder()

    # Bitmeyen batch'leri bekle, bitenlerin sonuçlarını sonuclar.jsonl'a yaz
    acik = [b for b in durum if b["model"] == ist.ad and not b.get("toplandi")]
    if not acik:
        return
    print(f"⏳ {len(acik)} batch bekleniyor (genelde 1 saat içinde biter, en fazla 24 saat). "
          "Ctrl+C ile çıkabilirsiniz; aynı komut beklemeye kaldığı yerden devam eder.")
    while acik:
        for b in list(acik):
            bilgi = ist.client.messages.batches.retrieve(b["id"])
            if bilgi.processing_status != "ended":
                c = bilgi.request_counts
                print(f"  {b['id']}: işleniyor {c.processing}, biten {c.succeeded}, "
                      f"hatalı {c.errored}", flush=True)
                continue
            with open(cikti / "sonuclar.jsonl", "a", encoding="utf-8") as f:
                for sonuc in ist.client.messages.batches.results(b["id"]):
                    m = b["istekler"].get(sonuc.custom_id)
                    if not m:
                        continue
                    tur = sonuc.result.type
                    if tur == "succeeded":
                        try:
                            cevap, kullanim, hata = ist.cevap_coz(sonuc.result.message)
                        except Exception as e:
                            u = sonuc.result.message.usage
                            cevap, kullanim = None, {"girdi": u.input_tokens,
                                                     "cikti": u.output_tokens}
                            hata = f"cozumleme: {e}"[:300]
                    else:
                        cevap, kullanim = None, {"girdi": 0, "cikti": 0}
                        hata = f"batch_{tur}"
                        if tur == "errored":
                            hata += f": {getattr(sonuc.result.error, 'type', '')}"
                    f.write(json.dumps(kayit_olustur(ist.ad, m, cevap, kullanim, hata, 0, True),
                                       ensure_ascii=False) + "\n")
            b["toplandi"] = True
            kaydet()
            acik.remove(b)
            print(f"✅ Batch tamamlandı ve sonuçlar yazıldı: {b['id']}")
        if acik:
            time.sleep(60)


# ------------------------------------------------------------------ BİRLEŞTİRME & OYLAMA

def birlestir(cikti):
    kayitlar = []
    onbellek_yol = cikti / "sonuclar.jsonl"
    if not onbellek_yol.exists():
        return
    with open(onbellek_yol, encoding="utf-8") as f:
        for satir in f:
            try:
                kayitlar.append(json.loads(satir))
            except json.JSONDecodeError:
                pass
    # Aynı (model, dosya, dilim) için son başarılı kayıt geçerli
    son = {}
    for r in kayitlar:
        k = (r["model"], r["dosya"], r["dilim"])
        if not r["hata"] or k not in son:
            son[k] = r
    kayitlar = list(son.values())

    bulgular = []
    for r in kayitlar:
        for d in (r["cevap"] or {}).get("defects", []):
            bulgular.append({
                "model": r["model"], "dosya": r["dosya"], "sayfa": r["sayfa"],
                "cihaz": r["cihaz"], "sablon": r["sablon"], "dilim": r["dilim"],
                "piksel": f"{r['y0']}-{r['y1']}", "tur": d.get("type", ""),
                "onem": d.get("severity", ""), "guven": d.get("confidence", ""),
                "konum": d.get("location", ""), "kanit": d.get("evidence_text", ""),
                "aciklama": d.get("description", ""),
                "okunan_metin": (r["cevap"] or {}).get("visible_text_sample", ""),
            })

    modeller = sorted({r["model"] for r in kayitlar})
    oylar = defaultdict(lambda: {"modeller": set(), "onem": Counter(), "ornek": ""})
    for b in bulgular:
        k = (b["dosya"], b["dilim"], b["tur"])
        oylar[k]["modeller"].add(b["model"])
        oylar[k]["onem"][b["onem"]] += 1
        oylar[k]["ornek"] = oylar[k]["ornek"] or f"{b['kanit']} | {b['aciklama']}"
    bakilan = defaultdict(set)                     # dilime bakan modeller (payda)
    for r in kayitlar:
        if not r["hata"]:
            bakilan[(r["dosya"], r["dilim"])].add(r["model"])
    oylama = []
    for (dosya, dilim, tur), v in oylar.items():
        bakan = len(bakilan[(dosya, dilim)]) or 1
        n = len(v["modeller"])
        oylama.append({
            "dosya": dosya, "dilim": dilim, "tur": tur, "oy": n, "bakan_model": bakan,
            "karar": "KESIN" if n >= 2 else "INCELE",
            "modeller": ",".join(sorted(v["modeller"])),
            "onem": v["onem"].most_common(1)[0][0], "ornek": v["ornek"][:300],
        })
    oylama.sort(key=lambda x: (-x["oy"], x["dosya"], x["dilim"]))

    def yaz(ad, satirlar, alanlar):
        with open(cikti / ad, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=alanlar, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(satirlar)

    yaz("bulgular.csv", bulgular, list(bulgular[0].keys()) if bulgular else ["model"])
    yaz("oylama.csv", oylama, ["karar", "oy", "bakan_model", "tur", "onem", "dosya", "dilim",
                                "modeller", "ornek"])

    L = ["=" * 70, "GÖRSEL DENETİM - AŞAMA 2 (YAPAY ZEKA) ÖZETİ", "=" * 70, ""]
    for m in modeller:
        mk = [r for r in kayitlar if r["model"] == m]
        basarili = [r for r in mk if not r["hata"]]
        mb = [b for b in bulgular if b["model"] == m]
        gir = sum(r["kullanim"]["girdi"] for r in mk)
        cik = sum(r["kullanim"]["cikti"] for r in mk)
        sure = [r["sure"] for r in basarili if r["sure"]]
        L.append(f"[{m}]")
        L.append(f"  istek: {len(mk)} | başarılı: {len(basarili)} | hatalı: {len(mk) - len(basarili)}")
        L.append(f"  bulgu: {len(mb)} | hata bulunan dilim: "
                 f"{len({(b['dosya'], b['dilim']) for b in mb})}/{len(basarili)}")
        L.append(f"  token: {gir:,} girdi, {cik:,} çıktı | ort. süre: "
                 f"{(sum(sure) / len(sure)) if sure else 0:.1f} sn")
        cm = m.partition(":")[2] if m.startswith("claude:") else ""
        if cm in CLAUDE_FIYAT:
            fi, fo = CLAUDE_FIYAT[cm]
            maliyet = sum((r["kullanim"]["girdi"] * fi + r["kullanim"]["cikti"] * fo) / 1e6
                          * (0.5 if r.get("toplu") else 1.0) for r in mk)
            toplu_n = sum(1 for r in mk if r.get("toplu"))
            L.append(f"  tahmini maliyet: ${maliyet:.2f} (çıktıya düşünme token'ları dahil"
                     + (f"; {toplu_n} istek toplu/Batch fiyatıyla" if toplu_n else "") + ")")
        turler = Counter(b["tur"] for b in mb)
        L.append("  türler: " + ", ".join(f"{t} {n}" for t, n in turler.most_common()))
        L.append("")
    kesin = [o for o in oylama if o["karar"] == "KESIN"]
    L.append(f"OYLAMA: {len(oylama)} (dilim, tür) bulgusu | {len(kesin)} tanesi 2+ modelce "
             f"bulundu (KESIN)")
    for o in kesin[:25]:
        L.append(f"  {o['oy']}/{o['bakan_model']} {o['tur']:20s} {o['dosya'][:70]} #{o['dilim']}")
    metin = "\n".join(L)
    (cikti / "ozet.txt").write_text(metin, encoding="utf-8")
    print("\n" + metin)


# ------------------------------------------------------------------ TAHMİN

def tahmin(a, ornekler):
    print(f"🔎 {len(ornekler)} görüntünün boyutları okunuyor (API çağrısı yapılmaz)...")
    dilim_sayisi, claude_token = 0, 0
    for o in ornekler:
        try:
            with Image.open(o["tam_yol"]) as im:
                w, h = im.size
        except Exception:
            continue
        hedef_w, dilim_h = DILIM.get(o["cihaz"], VARSAYILAN_DILIM)
        W = min(w, hedef_w)
        H = round(h * W / w)
        n = min(a.dilim, max(1, -(-H // dilim_h)))
        dilim_sayisi += n
        claude_token += n * (W * min(H, dilim_h) // 750 + 900)   # görsel + talimat
    cikti_token = dilim_sayisi * 350
    print(f"\n  Görüntü: {len(ornekler)} | Dilim (model başına istek): {dilim_sayisi}")
    print(f"  Claude tahmini token: ~{claude_token:,} girdi, ~{cikti_token:,} çıktı "
          f"(düşünme token'ları hariç)")
    for m, (fi, fo) in CLAUDE_FIYAT.items():
        print(f"    {m:18s} ~${claude_token / 1e6 * fi + cikti_token / 1e6 * fo:,.2f}")
    print("  Gemini: fiyatı Google'ın güncel fiyat sayfasından kontrol edin.")
    print(f"  Paralel {a.paralel} ile tahmini süre: ~{dilim_sayisi * 8 / a.paralel / 60:.0f} dk "
          f"(istek başına ~8 sn varsayımı)")
    print("\n  Önce --limit 10 ile deneme turu yapıp ozet.txt'deki gerçek token sayısına bakın.")


def gemini_dene():
    """Görsel analize aday Flash ve Gemma modellerine (önizleme/ses/görsel üretim hariç)
    birer GÖRSEL isteği atar: kırmızı bir kare gösterip rengini sorar. Böylece hem
    ücretsiz sürümde açık olup olmadığı hem de görsel okuyup okumadığı görülür."""
    from google import genai
    from google.genai import types
    client = genai.Client()
    haric = ("preview", "tts", "image", "latest", "transcribe", "robotics", "computer-use")
    adaylar = [m.name.split("/", 1)[1] for m in client.models.list()
               if "generateContent" in (getattr(m, "supported_actions", None) or [])
               and ("flash" in m.name or "gemma" in m.name)
               and not any(h in m.name for h in haric)]
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (220, 20, 20)).save(buf, "PNG")
    gorsel = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")
    print(f"🔎 {len(adaylar)} model deneniyor (her birine 1 küçük görsel isteği)...\n")
    for model in sorted(adaylar, reverse=True):
        try:
            r = client.models.generate_content(
                model=model,
                contents=[gorsel, "What is the main color of this image? Answer with one word."],
                config=types.GenerateContentConfig(
                    temperature=0,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
            cevap = (r.text or "").strip()
            gordu = "red" in cevap.lower() or "kırmızı" in cevap.lower()
            print(f"  {'✅' if gordu else '⚠️ '} {model:28s} "
                  f"{'görseli okuyor' if gordu else 'cevap verdi ama görseli okumadı'} "
                  f"({cevap[:20]!r})")
        except Exception as e:
            print(f"  ❌ {model:28s} {kisa_hata(f'{type(e).__name__}: {e}')[:220]}")
        time.sleep(4)
    print("\n✅ olan modellerden günlük sınırı en yüksek olanı seçin: "
          "AI Studio > Rate limits sayfasında model başına RPD (günlük istek) yazar.")


def main():
    p = argparse.ArgumentParser(description="Görsel denetim - yapay zeka analizi")
    p.add_argument("--ornekler", default="denetim_cikti/ornekler.csv")
    p.add_argument("--cikti", default="denetim_cikti/ai")
    p.add_argument("--klasor", help="Görüntüleri bu klasörden oku (ör. --kaydir ile yeniden "
                   "çekilmiş screenshots klasörü); dosya adları ornekler.csv ile aynı olmalı")
    p.add_argument("--modeller", default="gemini:gemma-4-31b-it",
                   help="Tarayan modeller, virgülle (varsayılan: görsel denetimde kullanılan Gemma 4)")
    p.add_argument("--limit", type=int, default=0, help="Yalnızca ilk N sayfa (deneme turu)")
    p.add_argument("--dilim", type=int, default=3, help="Görüntü başına en fazla dilim (vars. 3)")
    p.add_argument("--paralel", type=int, default=4, help="Bulut modelleri için eşzamanlı istek")
    p.add_argument("--claude-model", default=CLAUDE_MODEL)
    p.add_argument("--claude-effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="Claude düşünme düzeyi (boş = API varsayılanı)")
    p.add_argument("--gemini-model", default=GEMINI_MODEL)
    p.add_argument("--openai-url", default=os.environ.get("OPENAI_BASE_URL",
                                                          "https://api.openai.com/v1"),
                   help="openai:<model> için OpenAI uyumlu servis adresi (anahtar: OPENAI_API_KEY)")
    p.add_argument("--site-tanimi", default=SITE_TANIMI,
                   help="Talimatta sitenin tanımı (İngilizce), ör. 'an e-commerce website'")
    p.add_argument("--site-dili", default=SITE_DILI,
                   help="Sitenin beklenen dili (İngilizce adı), ör. 'German'")
    p.add_argument("--dakika-limit", type=int, default=0,
                   help="Bulut modeli başına dakikada en fazla istek (ücretsiz Gemini için ör. 8)")
    p.add_argument("--toplu", action="store_true",
                   help="Claude isteklerini Batch API ile gönder (%%50 ucuz, sonuç genelde "
                        "1 saat içinde; reddedilenlerde yedek modele geçiş yok)")
    p.add_argument("--hakem-ornek", type=int, default=0,
                   help="Hakeme her (şablon, cihaz, hata türü) grubundan en fazla N dilim gönder "
                        "(0 = hepsi). Ücretsiz kotalarda hakem yükünü büyük ölçüde azaltır.")
    p.add_argument("--hakem-grup", choices=["sablon", "tur"], default="sablon",
                   help="--hakem-ornek gruplaması: sablon=(şablon,cihaz,tür); "
                        "tur=(cihaz,tür) rastgele örnek -> hata türü başına isabet ölçümü")
    p.add_argument("--sadece-bakilamayan", action="store_true",
                   help="Hakeme yalnızca ana modelin hiç bakamadığı dilimleri gönder")
    p.add_argument("--hakem", help="Hakem modeli (ör. claude): yalnızca diğer modellerin "
                   "anlaşamadığı veya 'high' önem verdiği dilimlere sorulur")
    p.add_argument("--tahmin", action="store_true", help="Sadece maliyet/süre tahmini")
    p.add_argument("--gemini-listele", action="store_true", help="Gemini modellerini listele")
    p.add_argument("--gemini-dene", action="store_true",
                   help="Flash modellerine birer kısa istek atıp hangisinin çalıştığını göster")
    p.add_argument("--sadece-birlestir", action="store_true",
                   help="API çağırmadan mevcut sonuçlardan rapor üret")
    a = p.parse_args()
    global TALIMAT
    TALIMAT = TALIMAT_SABLONU.format(site=a.site_tanimi, dil=a.site_dili)

    if a.gemini_listele:
        from google import genai
        client = genai.Client()   # değişkende tutulmalı; yoksa liste gelmeden kapanır
        for m in client.models.list():
            if "generateContent" in (getattr(m, "supported_actions", None) or []):
                print(m.name)
        return

    if a.gemini_dene:
        gemini_dene()
        return


    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    if not a.sadece_birlestir:
        ornekler = ornekleri_oku(a.ornekler, a.limit, a.klasor)
        if a.hakem:
            hakem = istemci_olustur(a.hakem, a)
            filtre = hakem_dilimleri(cikti, hakem.ad, a.hakem_ornek, a.hakem_grup,
                                     a.sadece_bakilamayan)
            print(f"⚖️  Hakem {hakem.ad}: {len(filtre)} dilim anlaşmazlık veya yüksek önem içeriyor")
            cm = hakem.ad.partition(":")[2]
            if cm in CLAUDE_FIYAT:
                fi, fo = CLAUDE_FIYAT[cm]
                carpan = 0.5 if a.toplu else 1.0
                print(f"   tahmini maliyet: ~${len(filtre) * (2300 * fi + 1500 * fo) / 1e6 * carpan:.2f}"
                      " (dilim başına ~2300 girdi, ~1500 çıktı+düşünme token'ı varsayımı"
                      + ("; toplu/Batch fiyatı" if a.toplu else "") + ")")
            if a.tahmin:
                return
            calistir(a, ornekler, cikti, [hakem], filtre)
        else:
            if a.tahmin:
                tahmin(a, ornekler)
                return
            istemciler = [istemci_olustur(m.strip(), a)
                          for m in a.modeller.split(",") if m.strip()]
            calistir(a, ornekler, cikti, istemciler)
    birlestir(cikti)
    print(f"\n💾 Çıktılar: {cikti.resolve()}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
