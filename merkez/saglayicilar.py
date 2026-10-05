"""Yapay zekâ sağlayıcılarına bağlantı testi: anahtar geçerli mi, hangi modeller var?

Ek paket gerektirmez (urllib). Her sağlayıcının model listeleme ucunu çağırır;
ayarlarda yazılan model adının listede olup olmadığını da söyler.
"""

import json
import urllib.error
import urllib.request

ZAMAN_ASIMI = 15


def _getir(url, basliklar=None):
    istek = urllib.request.Request(url, headers=basliklar or {})
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as y:
        return json.loads(y.read().decode("utf-8"))


def _anthropic(ayar):
    if not ayar["anthropic_key"]:
        return None
    v = _getir("https://api.anthropic.com/v1/models?limit=100",
               {"x-api-key": ayar["anthropic_key"], "anthropic-version": "2023-06-01"})
    return [m["id"] for m in v.get("data", [])], ayar["claude_model"]


def _gemini(ayar):
    if not ayar["gemini_key"]:
        return None
    v = _getir("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
               {"x-goog-api-key": ayar["gemini_key"]})
    return ([m["name"].removeprefix("models/") for m in v.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])],
            ayar["gemini_model"])


def _openai(ayar):
    if not ayar["openai_url"] or ("api.openai.com" in ayar["openai_url"] and not ayar["openai_key"]):
        return None
    b = {"Authorization": f"Bearer {ayar['openai_key']}"} if ayar["openai_key"] else {}
    v = _getir(ayar["openai_url"].rstrip("/") + "/models", b)
    return [m["id"] for m in v.get("data", [])], ayar["openai_model"]


def _ollama(ayar):
    v = _getir(ayar["ollama_url"].rstrip("/") + "/api/tags")
    return [m["name"] for m in v.get("models", [])], ayar["ollama_model"]


SAGLAYICILAR = [
    ("Anthropic (claude)", _anthropic),
    ("Google Gemini (gemini)", _gemini),
    ("OpenAI uyumlu (openai:<model>)", _openai),
    ("Ollama yerel (ollama:<model>)", _ollama),
]


def test_et(ayar, yaz) -> int:
    calisan = 0
    for ad, fonk in SAGLAYICILAR:
        try:
            sonuc = fonk(ayar)
        except urllib.error.HTTPError as e:
            yaz(f"✖ {ad}: HTTP {e.code} {e.reason} (anahtar veya adres hatalı olabilir)\n")
            continue
        except Exception as e:
            yaz(f"✖ {ad}: bağlanılamadı ({e})\n")
            continue
        if sonuc is None:
            yaz(f"– {ad}: anahtar/adres girilmemiş, atlandı\n")
            continue
        modeller, secili = sonuc
        calisan += 1
        var = any(secili == m or m.startswith(secili + ":") for m in modeller)
        yaz(f"✔ {ad}: {len(modeller)} model. Ayarlardaki '{secili}': "
            f"{'listede var' if var else 'LİSTEDE YOK'}\n")
        for m in sorted(modeller)[:40]:
            yaz(f"     {m}\n")
        if len(modeller) > 40:
            yaz(f"     ... ve {len(modeller) - 40} model daha\n")
    yaz(f"\n{calisan} sağlayıcıya bağlanıldı.\n")
    return 0 if calisan else 1
