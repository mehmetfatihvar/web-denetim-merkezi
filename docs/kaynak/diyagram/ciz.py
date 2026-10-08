"""Teknik dokümandaki diyagramları (HTML) PNG'ye çevirir: python ciz.py"""
import pathlib
from playwright.sync_api import sync_playwright

KOK = pathlib.Path(__file__).parent
with sync_playwright() as p:
    t = p.chromium.launch()
    s = t.new_page(viewport={"width": 980, "height": 100}, device_scale_factor=2)
    for ad in ("mimari", "akis", "huni", "motor"):
        s.goto((KOK / f"{ad}.html").as_uri())
        s.screenshot(path=str(KOK.parent / "img" / f"teknik_{ad}.png"), full_page=True)
        print(ad)
    t.close()
