#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 GENEL SİTE KEŞİF ARACI  (kesif)
================================================================================
 Herhangi bir web sitesinin tıklanabilir sayfalarını keşfeder ve test aracının
 (tester_v3_evidence.py --source) okuyabileceği bir site haritası yazar.

 Yöntem: başlangıç adresinden itibaren sayfalardaki gerçek <a href>, <area href>
 ve GET formlarını genişlik öncelikli izler. URL tahmin etmez. İki çalışma biçimi:
   • istek (varsayılan) : requests + BeautifulSoup. Hızlı; sunucuda HTML üreten
                          (SSR) siteler için yeterli.
   • --tarayici         : Playwright/Chromium ile sayfayı çalıştırıp linkleri
                          JavaScript sonrası DOM'dan toplar (yalnızca tarayıcıda
                          içerik üreten SPA siteler için; daha yavaş).

 Sonsuz kombinasyon koruması (her sitede işe yarayan genel kurallar):
   • --haric           : bu düzenli ifadelere uyan adresler izlenmez
   • --yoksay-param    : bu sorgu parametreleri adresten silinir (utm_*, sort ...)
   • --sorgu-limiti    : aynı yolun en fazla N farklı sorgu varyasyonu alınır
   • --derinlik / --max-sayfa
 Belgeler (PDF, Word, Excel ...) sayfa listesine girmez, ayrı listelenir.

 ÇALIŞTIRMA:
     python kesif.py --url https://ornek.edu.tr/
     python kesif.py --url https://ornek.com/ --max-sayfa 5000 --isci 4 --rps 4
     python kesif.py --url https://spa.ornek.com/ --tarayici --ssl-yoksay
     python kesif.py --url https://ornek.com/ --haric "/arama" "/etiket/" --yoksay-param sort page_size

 ÇIKTI (--cikti, varsayılan site_haritasi.json):
     {"base_url", "olusturma", "ayarlar", "url_list": [...], "belgeler": [...],
      "hatalar": [...], "istatistik": {...}}
     Kesilirse aynı komutla devam eder (--taze ile baştan başlar).
================================================================================
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

BELGE_UZANTILARI = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
                    ".ods", ".odp", ".rtf", ".zip", ".rar", ".7z", ".csv", ".txt")
ATLANAN_UZANTILAR = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
                     ".mp4", ".mp3", ".avi", ".mov", ".webm", ".wav", ".css", ".js",
                     ".json", ".xml", ".woff", ".woff2", ".ttf", ".eot", ".exe", ".dmg")
VARSAYILAN_YOKSAY = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                     "fbclid", "gclid", "_ga", "sessionid", "jsessionid", "phpsessid"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " \
     "Chrome/130.0 Safari/537.36 SiteKesif/1.0"


# ------------------------------------------------------------------ URL kuralları

class Kurallar:
    def __init__(self, a):
        bas = urlparse(a.url)
        self.alanlar = {bas.netloc.lower()} | {h.lower() for h in a.alan}
        if a.alt_alanlar:
            self.kok_alan = bas.netloc.lower().split(":")[0]
        else:
            self.kok_alan = None
        self.haric = [re.compile(d) for d in a.haric]
        self.dahil = [re.compile(d) for d in a.dahil]
        self.yoksay = {p.lower() for p in a.yoksay_param}
        self.sorgusuz = a.sorgusuz
        self.sorgu_limiti = a.sorgu_limiti
        self.sorgu_sayaci = Counter()

    def alan_icinde(self, netloc):
        h = netloc.lower()
        if h in self.alanlar:
            return True
        return bool(self.kok_alan) and h.split(":")[0].endswith("." + self.kok_alan)

    def normallestir(self, adres, taban):
        """Bağıl adresi mutlak yapar; parça (#) ve yok sayılan parametreleri atar.
        İzlenmeyecek adreslerde (None, neden) döner."""
        adres = (adres or "").strip()
        if not adres or adres.startswith(("mailto:", "tel:", "javascript:", "data:", "sms:", "#")):
            return None, "sema"
        u = urlparse(urljoin(taban, adres))
        if u.scheme not in ("http", "https"):
            return None, "sema"
        if not self.alan_icinde(u.netloc):
            return None, "dis"
        yol = re.sub(r"/{2,}", "/", u.path or "/")
        sorgu = "" if self.sorgusuz else urlencode(sorted(
            (k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
            if k.lower() not in self.yoksay and not k.lower().startswith("utm_")))
        temiz = urlunparse((u.scheme, u.netloc.lower(), yol, "", sorgu, ""))
        if yol.lower().endswith(BELGE_UZANTILARI):
            return temiz, "belge"
        if yol.lower().endswith(ATLANAN_UZANTILAR):
            return None, "dosya"
        if any(d.search(temiz) for d in self.haric):
            return None, "haric"
        if self.dahil and not any(d.search(temiz) for d in self.dahil):
            return None, "haric"
        return temiz, "sayfa"

    def sorgu_izinli(self, adres):
        """Aynı yolun sorgu varyasyonlarını sınırla (filtre/sıralama kombinasyonları)."""
        u = urlparse(adres)
        if not u.query or not self.sorgu_limiti:
            return True
        anahtar = (u.netloc, u.path)
        self.sorgu_sayaci[anahtar] += 1
        return self.sorgu_sayaci[anahtar] <= self.sorgu_limiti


# ------------------------------------------------------------------ indiriciler

def html_linkleri(html_metni, taban):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_metni, "html.parser")
    b = soup.find("base", href=True)
    if b:
        taban = urljoin(taban, b["href"])
    linkler = [e["href"] for e in soup.find_all(["a", "area"], href=True)]
    for f in soup.find_all("form"):
        if (f.get("method") or "get").lower() == "get" and f.get("action"):
            linkler.append(f["action"])
    return taban, linkler


class IstekIndirici:
    def __init__(self, a):
        import requests
        import urllib3
        urllib3.disable_warnings()
        self.requests = requests
        self.yerel = threading.local()
        self.a = a

    def oturum(self):
        if not hasattr(self.yerel, "s"):
            s = self.requests.Session()
            s.verify = not self.a.ssl_yoksay
            s.headers.update({"User-Agent": self.a.user_agent, "Accept-Language": self.a.dil})
            self.yerel.s = s
        return self.yerel.s

    def getir(self, adres):
        r = self.oturum().get(adres, timeout=self.a.zaman_asimi, allow_redirects=True)
        tur = r.headers.get("content-type", "")
        if "html" not in tur:
            return r.status_code, r.url, tur, []
        taban, linkler = html_linkleri(r.text, r.url)
        return r.status_code, taban, tur, linkler

    def kapat(self):
        pass


class TarayiciIndirici:
    """Playwright ile: her işçi iş parçacığının kendi tarayıcısı olur."""

    def __init__(self, a):
        from playwright.sync_api import sync_playwright  # noqa: F401  (kurulu mu?)
        self.a = a
        self.yerel = threading.local()
        self.hepsi = []
        self.kilit = threading.Lock()

    def sayfa(self):
        if not hasattr(self.yerel, "sayfa"):
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            try:
                tarayici = pw.chromium.launch()
            except Exception:
                pw.stop()   # tekrar denemede aynı iş parçacığında yeniden başlatılabilsin
                raise
            ctx = tarayici.new_context(ignore_https_errors=self.a.ssl_yoksay,
                                       user_agent=self.a.user_agent, locale=self.a.dil)
            self.yerel.sayfa = ctx.new_page()
            with self.kilit:
                self.hepsi.append((pw, tarayici))
        return self.yerel.sayfa

    def getir(self, adres):
        s = self.sayfa()
        yanit = s.goto(adres, wait_until="networkidle", timeout=self.a.zaman_asimi * 1000)
        durum = yanit.status if yanit else 0
        linkler = s.eval_on_selector_all(
            "a[href], area[href]", "els => els.map(e => e.getAttribute('href'))")
        linkler += s.eval_on_selector_all(
            "form[action]:not([method=post]):not([method=POST])",
            "els => els.map(e => e.getAttribute('action'))")
        return durum, s.url, "text/html", linkler

    def kapat(self):
        for pw, tarayici in self.hepsi:
            try:
                tarayici.close()
                pw.stop()
            except Exception:
                pass


# ------------------------------------------------------------------ keşif

class Kesif:
    def __init__(self, a):
        self.a = a
        self.k = Kurallar(a)
        self.robots = None
        self.sayfalar = {}         # adres -> {"durum", "derinlik", "kaynak"}
        self.belgeler = {}         # adres -> kaynak sayfa
        self.hatalar = []
        self.dis = Counter()
        self.kuyruk = deque()
        self.gorulen = set()
        self.kilit = threading.Lock()
        self.sonraki_istek = 0.0

    # --- devam
    def yukle(self):
        if self.a.taze or not os.path.exists(self.a.cikti):
            return False
        try:
            with open(self.a.cikti, encoding="utf-8") as f:
                eski = json.load(f)
        except (OSError, ValueError):
            return False
        durum = eski.get("devam") or {}
        self.sayfalar = eski.get("sayfalar", {})
        self.belgeler = {b["url"]: b.get("kaynak", "") for b in eski.get("belgeler", [])}
        self.kuyruk = deque(tuple(x) for x in durum.get("kuyruk", []))
        self.gorulen = set(self.sayfalar) | {x[0] for x in self.kuyruk}
        if not self.kuyruk:
            return False
        print(f"[*] Devam: {len(self.sayfalar)} sayfa yapılmış, kuyrukta {len(self.kuyruk)}")
        return True

    def ekle(self, adres, derinlik, kaynak):
        if adres in self.gorulen:
            return
        if not self.k.sorgu_izinli(adres):
            return
        if self.robots and not self.robots.can_fetch(self.a.user_agent, adres):
            return
        self.gorulen.add(adres)
        self.kuyruk.append((adres, derinlik, kaynak))

    def hiz(self):
        if not self.a.rps:
            return
        with self.kilit:
            simdi = time.monotonic()
            bekle = max(0.0, self.sonraki_istek - simdi)
            self.sonraki_istek = max(simdi, self.sonraki_istek) + 1.0 / self.a.rps
        if bekle:
            time.sleep(bekle)

    def robots_oku(self):
        u = urlparse(self.a.url)
        rp = RobotFileParser(f"{u.scheme}://{u.netloc}/robots.txt")
        try:
            rp.read()
            self.robots = rp
            print("[*] robots.txt kurallarına uyuluyor")
        except Exception as e:
            print(f"[!] robots.txt okunamadı ({e}); kısıt uygulanmadı")

    def sitemap_oku(self, indirici):
        """robots.txt'deki ve /sitemap.xml'deki adresleri tohum olarak ekler."""
        import requests
        u = urlparse(self.a.url)
        adresler = [f"{u.scheme}://{u.netloc}/sitemap.xml"]
        if self.robots and self.robots.site_maps():
            adresler = self.robots.site_maps() + adresler
        bulunan, islenen = 0, set()
        while adresler and len(islenen) < 200:
            sm = adresler.pop(0)
            if sm in islenen:
                continue
            islenen.add(sm)
            try:
                r = requests.get(sm, timeout=self.a.zaman_asimi, verify=not self.a.ssl_yoksay,
                                 headers={"User-Agent": self.a.user_agent})
            except Exception:
                continue
            if r.status_code != 200:
                continue
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
                if loc.lower().endswith(".xml") or "sitemap" in loc.lower().rsplit("/", 1)[-1]:
                    adresler.append(loc)
                    continue
                temiz, tur = self.k.normallestir(loc, sm)
                if tur == "sayfa":
                    self.ekle(temiz, 1, "sitemap")
                    bulunan += 1
        print(f"[*] Site haritasından (sitemap) {bulunan} adres eklendi")

    def isle(self, indirici, adres, derinlik, kaynak):
        self.hiz()
        deneme = 0
        while True:
            try:
                durum, taban, tur, linkler = indirici.getir(adres)
                break
            except Exception as e:
                deneme += 1
                if deneme > self.a.tekrar:
                    return adres, derinlik, kaynak, None, str(e)[:200], []
                time.sleep(2 * deneme)
        return adres, derinlik, kaynak, durum, None, (taban, linkler) if linkler else []

    def sonucu_isle(self, sonuc):
        adres, derinlik, kaynak, durum, hata, linkbilgi = sonuc
        if hata:
            self.hatalar.append({"url": adres, "hata": hata, "kaynak": kaynak})
            return
        self.sayfalar[adres] = {"durum": durum, "derinlik": derinlik, "kaynak": kaynak}
        if not linkbilgi or (self.a.derinlik and derinlik >= self.a.derinlik):
            return
        taban, linkler = linkbilgi
        for l in linkler:
            temiz, t = self.k.normallestir(l, taban)
            if t == "sayfa":
                self.ekle(temiz, derinlik + 1, adres)
            elif t == "belge":
                self.belgeler.setdefault(temiz, adres)
            elif t == "dis":
                self.dis[urlparse(urljoin(taban, l)).netloc] += 1

    def kaydet(self, bitti=False):
        url_list = sorted(u for u, s in self.sayfalar.items()
                          if not self.a.yalniz_basarili or (s["durum"] or 0) < 400)
        veri = {
            "base_url": self.a.url,
            "olusturma": datetime.now().isoformat(timespec="seconds"),
            "ayarlar": {k: v for k, v in vars(self.a).items() if k != "cikti"},
            "istatistik": {
                "sayfa": len(self.sayfalar), "url_list": len(url_list),
                "belge": len(self.belgeler), "hata": len(self.hatalar),
                "durumlar": dict(Counter(str(s["durum"]) for s in self.sayfalar.values())),
                "dis_alanlar": dict(self.dis.most_common(30)),
                "tamamlandi": bitti,
            },
            "url_list": url_list,
            "belgeler": [{"url": u, "kaynak": k} for u, k in sorted(self.belgeler.items())],
            "hatalar": self.hatalar[-2000:],
            "sayfalar": self.sayfalar,
            "devam": {} if bitti else {"kuyruk": list(self.kuyruk)},
        }
        gecici = self.a.cikti + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
        os.replace(gecici, self.a.cikti)
        return veri["istatistik"]

    def calistir(self):
        a = self.a
        indirici = TarayiciIndirici(a) if a.tarayici else IstekIndirici(a)
        if a.robots:
            self.robots_oku()
        if not self.yukle():
            for bas in [a.url] + a.ek_url:
                temiz, tur = self.k.normallestir(bas, a.url)
                if temiz:
                    self.ek_tohum(temiz)
            if a.sitemap:
                self.sitemap_oku(indirici)
        print(f"[*] Keşif: {a.url}  ({'tarayıcı' if a.tarayici else 'istek'} modu, "
              f"{a.isci} işçi, en fazla {a.max_sayfa} sayfa)")
        bas_zaman, son_kayit = time.time(), time.time()
        try:
            with ThreadPoolExecutor(max_workers=a.isci) as havuz:
                bekleyen = set()
                while (self.kuyruk or bekleyen) and len(self.sayfalar) < a.max_sayfa:
                    while self.kuyruk and len(bekleyen) < a.isci * 2 and \
                            len(self.sayfalar) + len(bekleyen) < a.max_sayfa:
                        adres, d, kaynak = self.kuyruk.popleft()
                        bekleyen.add(havuz.submit(self.isle, indirici, adres, d, kaynak))
                    if not bekleyen:
                        break
                    biten, bekleyen = wait(bekleyen, return_when=FIRST_COMPLETED)
                    onceki = len(self.sayfalar)
                    for f in biten:
                        self.sonucu_isle(f.result())
                    n = len(self.sayfalar)
                    if n // 50 > onceki // 50:
                        hiz = n / max(time.time() - bas_zaman, 1)
                        print(f"    {n} sayfa | kuyruk {len(self.kuyruk)} | belge "
                              f"{len(self.belgeler)} | hata {len(self.hatalar)} | {hiz:.1f} sayfa/sn",
                              flush=True)
                    if time.time() - son_kayit > 30:
                        self.kaydet()
                        son_kayit = time.time()
                for f in bekleyen:
                    self.sonucu_isle(f.result())
        except KeyboardInterrupt:
            print("\n[!] Durduruldu; aynı komutla kaldığı yerden devam edilebilir.")
            self.kaydet()
            indirici.kapat()
            sys.exit(130)
        indirici.kapat()
        bitti = not self.kuyruk
        ist = self.kaydet(bitti=bitti)
        print("=" * 70)
        print(f"[✓] {ist['sayfa']} sayfa ziyaret edildi, haritaya {ist['url_list']} sayfa yazıldı")
        print(f"    Belge: {ist['belge']} | Hata: {ist['hata']} | Durum kodları: {ist['durumlar']}")
        if not bitti:
            print(f"[!] --max-sayfa sınırına ulaşıldı; kuyrukta {len(self.kuyruk)} adres kaldı. "
                  "Sınırı artırıp aynı komutla devam edebilirsiniz.")
        print(f"    Çıktı: {os.path.abspath(a.cikti)}")
        print(f"    Sıradaki: python tester_v3_evidence.py --source {a.cikti} --limit 50")

    def ek_tohum(self, adres):
        self.gorulen.add(adres)
        self.kuyruk.append((adres, 0, ""))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Genel web sitesi keşif aracı (site haritası üretir)")
    ap.add_argument("--url", required=True, help="Başlangıç adresi, ör. https://ornek.edu.tr/")
    ap.add_argument("--ek-url", nargs="*", default=[], help="Ek başlangıç adresleri")
    ap.add_argument("--cikti", default="site_haritasi.json", help="Çıktı JSON dosyası")
    ap.add_argument("--max-sayfa", type=int, default=20000, help="En fazla ziyaret edilecek sayfa")
    ap.add_argument("--derinlik", type=int, default=0, help="En fazla link derinliği (0 = sınırsız)")
    ap.add_argument("--isci", type=int, default=4, help="Eşzamanlı istek sayısı")
    ap.add_argument("--rps", type=float, default=5, help="Saniyede en fazla istek (0 = sınırsız)")
    ap.add_argument("--zaman-asimi", type=int, default=20, help="İstek başına saniye")
    ap.add_argument("--tekrar", type=int, default=2, help="Hatalı istekte tekrar sayısı")
    ap.add_argument("--tarayici", action="store_true",
                    help="Linkleri JavaScript çalıştıktan sonra topla (SPA siteler için, Playwright)")
    ap.add_argument("--ssl-yoksay", action="store_true", help="Sertifika hatalarını yok say (self-signed)")
    ap.add_argument("--alan", nargs="*", default=[], help="Site içi sayılacak ek alan adları")
    ap.add_argument("--alt-alanlar", action="store_true", help="Alt alan adlarını da site içi say")
    ap.add_argument("--haric", nargs="*", default=[], help="İzlenmeyecek adres düzenli ifadeleri")
    ap.add_argument("--dahil", nargs="*", default=[],
                    help="Yalnızca bu düzenli ifadelere uyan adresleri izle (boş = hepsi)")
    ap.add_argument("--yoksay-param", nargs="*", default=VARSAYILAN_YOKSAY,
                    help="Adresten silinecek sorgu parametreleri")
    ap.add_argument("--sorgusuz", action="store_true", help="Tüm sorgu parametrelerini sil")
    ap.add_argument("--sorgu-limiti", type=int, default=50,
                    help="Aynı yolun en fazla kaç sorgu varyasyonu izlensin (0 = sınırsız)")
    ap.add_argument("--sitemap", action="store_true", help="sitemap.xml adreslerini de tohum olarak ekle")
    ap.add_argument("--robots", action="store_true", help="robots.txt kurallarına uy")
    ap.add_argument("--yalniz-basarili", action="store_true",
                    help="4xx/5xx dönen sayfaları haritaya yazma (varsayılan: yazılır, test aracı "
                         "bunları kırık sayfa olarak raporlar)")
    ap.add_argument("--user-agent", default=UA)
    ap.add_argument("--dil", default="tr-TR", help="Accept-Language / tarayıcı yerel ayarı")
    ap.add_argument("--taze", action="store_true", help="Var olan çıktıyı yok say, baştan başla")
    return ap.parse_args(argv)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    Kesif(parse_args()).calistir()
