"""Adımları sırayla çalıştıran motor (arayüzden bağımsız).

Her komutun çıktısı canlı olarak `yaz` geri çağrısına ve bir kayıt dosyasına
aktarılır. Çıktıdan ilerleme, kalan süre ve hata/uyarılar çıkarılıp `olay`
geri çağrısına sözlük olarak verilir:
  {"tur": "basladi", "adimlar": [(id, ad), ...]}
  {"tur": "adim_basladi", "id", "ad", "sira", "toplam"}
  {"tur": "ilerleme", "id", "biten", "toplam", "oran_adim", "oran_genel", "kalan_sn", "gecen_sn"}
  {"tur": "sorun", "id", "ad", "seviye": "hata"|"uyari", "satir", "zaman"}
  {"tur": "adim_bitti", **sonuç kaydı}          (bkz. AdimSonucu)
  {"tur": "bitti", "tamam": bool, "sonuclar": [...]}
Durdurma, sürecin tüm alt süreçleriyle birlikte sonlandırılmasıdır
(Playwright tarayıcıları, docker run ...).
"""

import codecs
import os
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from .adimlar import Adim, Komut
from .ayarlar import Klasorler
from .izleme import SatirBolucu, SureTahmini, ilerleme_oku, sorun_turu, sure_metni

SORUN_SINIRI = 300      # adım başına saklanan en fazla hata/uyarı satırı (sayı yine tam tutulur)

WINDOWS = os.name == "nt"


PROGRAM_IPUCU = {
    "docker": "Docker Desktop kurulu ve açık mı? Kurmak istemiyorsanız Ayarlar'da Bologna "
              "çalıştırma biçimini 'yerel' yapın (Go ve PostgreSQL gerekir).",
    "go": "Go kurulu mu (go.dev/dl)? Ya da Ayarlar'da Bologna çalıştırma biçimini 'docker' yapın.",
}


class Durduruldu(Exception):
    pass


class Calistirici:
    def __init__(self, yaz: Callable[[str], None], olay: Optional[Callable[[dict], None]] = None):
        self.yaz = yaz                     # metin parçası (\r ve \n içerebilir)
        self.olay = olay or (lambda o: None)
        self.surec: Optional[subprocess.Popen] = None
        self.durdur_istendi = False
        self.kilit = threading.Lock()
        self.kayit = None
        self.kayit_yolu: Optional[Path] = None
        self.sonuclar: List[dict] = []
        self._izleme_sifirla()

    # ------------------------------------------------------------ dış arayüz
    def calistir(self, adimlar: List[Adim], ayar: dict, devam_et: bool = False) -> bool:
        """Adımları sırayla çalıştırır. Hepsi başarılıysa True döner."""
        self.durdur_istendi = False
        self.sonuclar = []
        self.ayrintili = bool(ayar.get("ayrintili"))
        self.olay({"tur": "basladi", "adimlar": [(a.id, a.ad) for a in adimlar]})
        hepsi_tamam = True
        for i, adim in enumerate(adimlar, 1):
            if self.durdur_istendi:
                break
            sonuc = self._adim(adim, ayar, i, len(adimlar))
            if sonuc == "durdu":
                hepsi_tamam = False
                break
            if sonuc != "basarili":
                hepsi_tamam = False
                if not devam_et:
                    self.yaz(f"\n■ '{adim.ad}' başarısız oldu; sıradaki adımlar çalıştırılmadı.\n")
                    break
        tamam = hepsi_tamam and not self.durdur_istendi
        self._ozet_yaz()
        self.olay({"tur": "bitti", "tamam": tamam, "sonuclar": list(self.sonuclar)})
        return tamam

    def durdur(self):
        self.durdur_istendi = True
        with self.kilit:
            s = self.surec
        if s and s.poll() is None:
            self.yaz("\n■ Durduruluyor...\n")
            _agaci_sonlandir(s)

    @property
    def calisiyor(self) -> bool:
        with self.kilit:
            return self.surec is not None and self.surec.poll() is None

    # ------------------------------------------------------------ iç işler
    def _izleme_sifirla(self, adim=None, sira=1, toplam=1, komut_sayisi=1):
        self.adim, self.sira, self.toplam = adim, sira, toplam
        self.komut_sayisi, self.komut_no = max(komut_sayisi, 1), 0
        self.bolucu = SatirBolucu()
        self._bekleyen_cr = ""
        self.tahmin = SureTahmini()
        self.adim_bas = time.monotonic()
        self.hata_sayisi = self.uyari_sayisi = 0
        self.sorunlar: List[dict] = []
        self.son_satirlar: List[str] = []
        self.son_ilerleme = 0.0
        self.en_cok = (None, 0)          # (toplam, biten): bu komutta görülen en büyük sayı

    def _adim(self, adim: Adim, ayar: dict, sira: int, toplam: int) -> str:
        self.komut_metinleri = []
        try:
            komutlar = adim.komutlar(ayar)
        except Exception as e:  # ayar hatası (ör. geçersiz sayı) adımı düşürür, programı değil
            self._izleme_sifirla(adim, sira, toplam)
            self.yaz(f"\n✖ {adim.ad}: komut hazırlanamadı: {e}\n")
            self._sorun("hata", f"Komut hazırlanamadı: {e}")
            return self._adim_bitir(adim, ayar, "hatali", 0.0)
        self._izleme_sifirla(adim, sira, toplam, len(komutlar))
        self.komut_metinleri = []
        for k in komutlar:
            try:
                self.komut_metinleri.append(k.goster())
            except Exception:
                pass
        self._kayit_ac(adim, ayar)
        self.olay({"tur": "adim_basladi", "id": adim.id, "ad": adim.ad, "sira": sira, "toplam": toplam})
        self._yaz_ve_kaydet(f"\n{'═' * 70}\n▶ [{sira}/{toplam}] {adim.ad}"
                            f"   ({datetime.now():%H:%M:%S})\n{'═' * 70}\n")
        bas = time.time()
        sonuc = "basarili"
        komut = None
        try:
            for j, komut in enumerate(komutlar, 1):
                if self.durdur_istendi:
                    raise Durduruldu()
                self.komut_no = j - 1
                self.en_cok = (None, 0)
                # Önceki komut ilerleme satırı basmadan bittiyse (ör. tam testte zaten yapılmış
                # parça) bu sıçrama gerçek iş değildir: kalan süre hesabına hız olarak girmez.
                self._ilerleme_bildir(None, atlama=True)
                baslik = komut.aciklama or (f"Komut {j}/{len(komutlar)}" if len(komutlar) > 1 else "")
                if baslik:
                    self._yaz_ve_kaydet(f"── {baslik}\n")
                kod = self._komut(komut)
                if self.durdur_istendi:
                    raise Durduruldu()
                if kod != 0:
                    self._yaz_ve_kaydet(f"\n✖ Çıkış kodu {kod}\n")
                    self._sorun("hata", f"Komut {kod} çıkış koduyla bitti: {komut.goster()[:200]}")
                    sonuc = "hatali"
                    break
        except Durduruldu:
            sonuc = "durdu"
        except FileNotFoundError as e:
            # Windows'ta e.filename çoğu zaman boş gelir: programın adı komuttan alınır
            ad = e.filename or (komut.argv[0] if komut is not None and komut.argv else "?")
            ipucu = PROGRAM_IPUCU.get(Path(str(ad)).stem.lower(), "Kurulu ve PATH'te mi?")
            self._yaz_ve_kaydet(f"\n✖ Program bulunamadı: {ad}. {ipucu}\n")
            self._sorun("hata", f"Program bulunamadı: {ad}. {ipucu}")
            sonuc = "hatali"
        except Exception as e:
            self._yaz_ve_kaydet(f"\n✖ Beklenmeyen hata: {e}\n")
            self._sorun("hata", f"Beklenmeyen hata: {e}")
            sonuc = "hatali"
        return self._adim_bitir(adim, ayar, sonuc, time.time() - bas)

    def _adim_bitir(self, adim, ayar, sonuc, sure) -> str:
        isaret = {"basarili": "✔", "hatali": "✖", "durdu": "■"}[sonuc]
        metin = {"basarili": "başarılı", "hatali": "başarısız", "durdu": "durduruldu"}[sonuc]
        sorun = f", {self.hata_sayisi} hata, {self.uyari_sayisi} uyarı" \
            if self.hata_sayisi or self.uyari_sayisi else ""
        self._yaz_ve_kaydet(f"{isaret} {adim.ad}: {metin} ({_sure(sure)}{sorun})\n")
        if sonuc == "hatali" and self.son_satirlar:
            self._yaz_ve_kaydet("   Son çıktı satırları (hata ayıklama için):\n" +
                                "".join(f"   │ {s}\n" for s in self.son_satirlar[-12:]))
        if sonuc != "basarili" and self.kayit_yolu:
            self._yaz_ve_kaydet(f"   Ayrıntılı kayıt: {self.kayit_yolu}\n")
        self._kayit_kapat()
        try:
            ciktilar = [str(p) for p in adim.ciktilar(ayar) if p.exists()]
        except Exception:
            ciktilar = []
        kayit = {"id": adim.id, "ad": adim.ad, "sonuc": sonuc, "sure_sn": sure,
                 "hata": self.hata_sayisi, "uyari": self.uyari_sayisi,
                 "sorunlar": list(self.sorunlar), "ciktilar": ciktilar,
                 "kayit": str(self.kayit_yolu) if self.kayit_yolu else "",
                 "bitis": datetime.now().strftime("%H:%M:%S"), "rapor": ""}
        try:   # her adım, ne üretirse üretsin, görülebilir bir rapor bırakır
            from .adim_raporu import uret
            kayit["rapor"] = str(uret(Klasorler(ayar).adim_raporlari, kayit,
                                      getattr(self, "komut_metinleri", []), adim.aciklama,
                                      f'{ayar.get("site_adi", "")} ({ayar.get("site_url", "")})'))
            self.yaz(f"   Adım raporu: {kayit['rapor']}\n")
        except Exception as e:      # rapor yazılamasa da adımın sonucu kaybolmasın
            self.yaz(f"   [!] Adım raporu yazılamadı: {e}\n")
        self.sonuclar.append(kayit)
        self.olay({"tur": "adim_bitti", **kayit})
        return sonuc

    def _ozet_yaz(self):
        if len(self.sonuclar) < 2:
            return
        self.yaz(f"\n{'─' * 70}\nÖZET\n")
        for r in self.sonuclar:
            isaret = {"basarili": "✔", "hatali": "✖", "durdu": "■"}[r["sonuc"]]
            self.yaz(f"  {isaret} {r['ad']:45s} {_sure(r['sure_sn']):>10s}   "
                     f"hata {r['hata']}, uyarı {r['uyari']}\n")

    # ------------------------------------------------------------ izleme
    def _cikti(self, metin: str, son: bool = False):
        """Aracın çıktısı: kayda yaz, satırlardan ilerleme ve sorun çıkar.
        Windows satır sonları (\r\n) \n'ye çevrilir; tek başına \r (aynı satırı güncelleyen
        ilerleme çubukları) korunur. Parça sonundaki \r, ardından \n gelebileceği için bekletilir."""
        metin = self._bekleyen_cr + metin
        self._bekleyen_cr = ""
        if metin.endswith("\r") and not son:
            metin, self._bekleyen_cr = metin[:-1], "\r"
        metin = metin.replace("\r\n", "\n")
        self._yaz_ve_kaydet(metin)
        for satir in self.bolucu.ekle(metin):
            self._satir_isle(satir)

    def _satir_isle(self, satir: str):
        if satir.strip():
            self.son_satirlar.append(satir)
            del self.son_satirlar[:-40]
        ilerleme = ilerleme_oku(satir)
        if ilerleme:
            self._ilerleme_bildir(ilerleme)
        tur = sorun_turu(satir)
        if tur:
            self._sorun(tur, satir.strip())

    def _sorun(self, seviye: str, satir: str):
        if seviye == "hata":
            self.hata_sayisi += 1
        else:
            self.uyari_sayisi += 1
        ad = self.adim.ad if self.adim else ""
        kayit = {"tur": "sorun", "id": self.adim.id if self.adim else "", "ad": ad,
                 "seviye": seviye, "satir": satir[:500], "zaman": datetime.now().strftime("%H:%M:%S")}
        if len(self.sorunlar) < SORUN_SINIRI:
            self.sorunlar.append(kayit)
            self.olay(kayit)
        self.olay({"tur": "sayac", "hata": self.hata_sayisi, "uyari": self.uyari_sayisi})

    def _ilerleme_bildir(self, ilerleme, atlama=False):
        """Adım oranı = (biten komutlar + bu komutun oranı) / komut sayısı.

        Eşzamanlı çalışan araçlar "[i/n]" satırlarını sırasız basabilir (yavaş bir sayfa
        geç biter). Aynı sayaç içinde sayı geri gitmez, adım oranı da hiç geri gitmez;
        yoksa yüzde ileri geri oynar ve kalan süre bozulur.
        """
        biten = toplam = None
        komut_orani = 0.0
        if ilerleme:
            biten, toplam = ilerleme
            if self.en_cok[0] is None:
                # Komutun ilk ilerleme satırı: kaldığı yerden devam eden araçlar doğrudan
                # "[500/1000]" ile başlar; önceden yapılmış kısım hız sayılmaz.
                atlama = True
            if self.en_cok[0] == toplam:
                biten = max(biten, self.en_cok[1])
            self.en_cok = (toplam, biten)
            komut_orani = biten / toplam
        oran = min(1.0, (self.komut_no + komut_orani) / self.komut_sayisi)
        oran = max(oran, self.son_ilerleme)
        self.son_ilerleme = oran
        self.tahmin.ekle(oran, atlama=atlama)
        genel = ((self.sira - 1) + oran) / max(self.toplam, 1)
        self.olay({"tur": "ilerleme", "id": self.adim.id if self.adim else "", "biten": biten,
                   "toplam": toplam, "oran_adim": oran, "oran_genel": genel,
                   "kalan_sn": self.tahmin.kalan(), "gecen_sn": time.monotonic() - self.adim_bas,
                   "komut_no": self.komut_no + 1, "komut_sayisi": self.komut_sayisi})

    def _komut(self, komut: Komut) -> int:
        if komut.fonksiyon:
            kod = int(komut.fonksiyon(self._cikti) or 0)
            for satir in self.bolucu.bitir():
                self._satir_isle(satir)
            return kod
        self._yaz_ve_kaydet(f"$ {komut.goster()}\n")
        if self.ayrintili:
            # API anahtarları kayda asla açık yazılmaz
            ek_env = ", ".join(f"{k}={'***' if 'KEY' in k else v}" for k, v in komut.env.items())
            self._yaz_ve_kaydet(f"  [ayrıntı] klasör: {komut.cwd}\n"
                                f"  [ayrıntı] ek ortam: {ek_env or '-'}\n"
                                f"  [ayrıntı] argümanlar: {komut.argv}\n")
        env = dict(os.environ)
        env.update({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        env.update(komut.env)
        ek = {}
        if WINDOWS:
            ek["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # pencere açma
        else:
            ek["start_new_session"] = True
        Path(komut.cwd).mkdir(parents=True, exist_ok=True)
        s = subprocess.Popen(komut.argv, cwd=str(komut.cwd), env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **ek)
        with self.kilit:
            self.surec = s
        cozucu = codecs.getincrementaldecoder("utf-8")(errors="replace")

        def oku():
            while True:
                parca = s.stdout.read1(4096)
                if not parca:
                    break
                self._cikti(cozucu.decode(parca))
            self._cikti(cozucu.decode(b"", final=True), son=True)
            for satir in self.bolucu.bitir():
                self._satir_isle(satir)

        # Çıktı ayrı iş parçacığında okunur: süreç bitse de arka planda bıraktığı bir alt
        # süreç boruyu açık tutabilir; o durumda en fazla birkaç saniye beklenir.
        okuyucu = threading.Thread(target=oku, daemon=True)
        okuyucu.start()
        try:
            kod = s.wait()
            okuyucu.join(timeout=3)
            if not okuyucu.is_alive():
                s.stdout.close()
            return kod
        finally:
            with self.kilit:
                self.surec = None

    def _kayit_ac(self, adim: Adim, ayar: dict):
        try:
            klasor = Klasorler(ayar).kayitlar
            klasor.mkdir(parents=True, exist_ok=True)
            self.kayit_yolu = klasor / f"{datetime.now():%Y%m%d_%H%M%S}_{adim.id}.log"
            self.kayit = open(self.kayit_yolu, "w", encoding="utf-8")
        except OSError:
            self.kayit = None
            self.kayit_yolu = None

    def _kayit_kapat(self):
        if self.kayit:
            self.kayit.close()
            self.kayit = None

    def _yaz_ve_kaydet(self, metin: str):
        if not metin:
            return
        self.yaz(metin)
        if self.kayit:
            try:
                self.kayit.write(metin)
                self.kayit.flush()
            except OSError:
                pass


def _agaci_sonlandir(s: subprocess.Popen, bekle: float = 5.0):
    """Önce nazikçe (Ctrl+C/Ctrl+Break: araçlar kısmi sonucu kaydeder), olmazsa zorla."""
    try:
        if WINDOWS:
            s.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(s.pid, signal.SIGINT)
    except (OSError, ValueError):
        pass
    try:
        s.wait(timeout=bekle)
    except subprocess.TimeoutExpired:
        pass
    # Ana süreç kapanmış olsa da gruptaki artıkları (tarayıcılar, arka plan işleri) temizle
    try:
        if WINDOWS:
            if s.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(s.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(s.pid, signal.SIGKILL)
    except OSError:
        pass


_sure = sure_metni
