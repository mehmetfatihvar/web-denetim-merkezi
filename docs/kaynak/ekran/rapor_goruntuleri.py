"""Kırık link ve belge raporlarının ekran görüntüsü (Playwright). Kullanım:
  python rapor_goruntuleri.py IMG_KLASORU CIKTI_KOKU"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

img, kok = Path(sys.argv[1]), Path(sys.argv[2])
with sync_playwright() as p:
    t = p.chromium.launch()
    s = t.new_page(viewport={"width": 1320, "height": 820})
    for html, ad in ((kok / "linkdenetim" / "kirik_link_raporu.html", "19_kirik_link_raporu"),
                     (kok / "denetim" / "belge_raporu.html", "20_belge_raporu")):
        s.goto(html.resolve().as_uri()); s.wait_for_timeout(400)
        s.screenshot(path=str(img / f"{ad}.png"))
    t.close()
