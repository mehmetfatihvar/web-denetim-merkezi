"""Bu bilgisayarda gerekenler kurulu mu? (Python paketleri, Chromium, Go, Docker)

Program başka bilgisayarlara taşındığında ilk açılışta eksikler buradan bulunur ve
arayüzde uyarı olarak gösterilir. Kontrol, araçları çalıştıracak Python ile yapılır.
"""

import json
import shutil
import subprocess

# Araçların ihtiyaç duyduğu paketler: (import adı, pip adı, ne için)
PAKETLER = [
    ("playwright", "playwright", "tarayıcıyla test (zorunlu)"),
    ("pandas", "pandas", "Excel raporu"),
    ("openpyxl", "openpyxl", "Excel raporu"),
    ("requests", "requests", "site keşfi"),
    ("bs4", "beautifulsoup4", "site keşfi"),
    ("PIL", "pillow", "görsel denetim"),
    ("anthropic", "anthropic", "Claude (isteğe bağlı)"),
    ("google.genai", "google-genai", "Gemini (isteğe bağlı)"),
    ("ollama", "ollama", "Ollama (isteğe bağlı)"),
]
ISTEGE_BAGLI = {"anthropic", "google.genai", "ollama"}

_BETIK = r"""
import importlib.util, json, os, sys
sonuc = {"surum": sys.version.split()[0], "eksik": [], "chromium": None}
for ad in %s:
    try:
        bulundu = importlib.util.find_spec(ad) is not None
    except (ImportError, ValueError):
        bulundu = False
    if not bulundu:
        sonuc["eksik"].append(ad)
if "playwright" not in sonuc["eksik"]:
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        try:
            sonuc["chromium"] = os.path.exists(p.chromium.executable_path)
        finally:
            p.stop()
    except Exception:
        sonuc["chromium"] = False
print(json.dumps(sonuc))
"""


def kontrol(python: str, zaman_asimi: int = 60) -> dict:
    """{'python': bool, 'surum', 'eksik': [...], 'chromium': bool|None, 'go': bool, 'docker': bool}"""
    sonuc = {"python": False, "surum": "", "eksik": [p[0] for p in PAKETLER], "chromium": None,
             "go": shutil.which("go") is not None, "docker": shutil.which("docker") is not None}
    try:
        cikti = subprocess.run([python, "-c", _BETIK % [p[0] for p in PAKETLER]], capture_output=True,
                               text=True, timeout=zaman_asimi, encoding="utf-8", errors="replace")
        veri = json.loads(cikti.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return sonuc
    sonuc.update(python=True, surum=veri["surum"], eksik=veri["eksik"], chromium=veri["chromium"])
    return sonuc


def sorunlar(durum: dict) -> list:
    """Kullanıcıya gösterilecek eksikler (isteğe bağlı paketler hariç)."""
    s = []
    if not durum["python"]:
        return ["Ayarlardaki Python yorumlayıcısı çalıştırılamadı."]
    zorunlu = [p for p in durum["eksik"] if p not in ISTEGE_BAGLI]
    if zorunlu:
        adlar = {p[0]: p[1] for p in PAKETLER}
        s.append("Eksik Python paketleri: " + ", ".join(adlar[p] for p in zorunlu))
    if durum["chromium"] is False:
        s.append("Playwright Chromium tarayıcısı indirilmemiş")
    return s


def rapor(ayar: dict, yaz) -> int:
    d = kontrol(ayar["python"])
    yaz(f"Python       : {ayar['python']} ({d['surum'] or 'çalıştırılamadı'})\n")
    for ad, pip_adi, amac in PAKETLER:
        durum = "eksik" if ad in d["eksik"] else "kurulu"
        isaret = "✔" if durum == "kurulu" else ("–" if ad in ISTEGE_BAGLI else "✖")
        yaz(f"  {isaret} {pip_adi:16s} {durum:7s} {amac}\n")
    chromium = {True: "kurulu", False: "EKSİK", None: "denetlenemedi (playwright yok)"}[d["chromium"]]
    yaz(f"Chromium     : {chromium}\n")
    yaz(f"Go           : {'var' if d['go'] else 'yok'} (Bologna yerel modu için)\n")
    yaz(f"Docker       : {'var' if d['docker'] else 'yok'} (Bologna Docker modu için)\n")
    eksik = sorunlar(d)
    if eksik:
        yaz("\n" + "\n".join(f"⚠ {x}" for x in eksik) + "\nÇözüm: 'Bağımlılıkları kur' adımını çalıştırın.\n")
        return 1
    yaz("\nTest ve denetim için gerekenler kurulu.\n")
    return 0
