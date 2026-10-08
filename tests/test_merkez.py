"""Web Denetim Merkezi birim testleri (ek paket gerektirmez).

Çalıştırma (program/ klasöründen):  python -m unittest discover -s tests -v
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from argparse import Namespace
from pathlib import Path

PROGRAM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROGRAM))
sys.path.insert(0, str(PROGRAM / "tools"))

from merkez import ayarlar as A  # noqa: E402
from merkez import yollar  # noqa: E402
from merkez.adimlar import ADIM, ADIMLAR, GRUPLAR, TAM_HAT, harita_url_sayisi, tam_hat  # noqa: E402
TAM_HAT_SIRA = TAM_HAT.index
from merkez.calistirici import Calistirici  # noqa: E402
from merkez.adimlar import Adim, Komut  # noqa: E402


class GeciciKlasor(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.t = Path(self._t.name)
        self.profiller = self.t / "profiller"
        self.ayar_dosyasi = self.t / "ayarlar.json"

    def tearDown(self):
        self._t.cleanup()


class AyarTestleri(GeciciKlasor):
    def test_yeni_profil_ve_yukleme(self):
        kimlik = A.yeni_profil("Örnek Üniversitesi", "https://www.ornek.edu.tr/", klasor=self.profiller)
        self.assertEqual(kimlik, "ornek-universitesi")
        ayar = A.yukle(self.ayar_dosyasi, self.profiller, profil=kimlik)
        self.assertEqual(ayar["site_url"], "https://www.ornek.edu.tr/")
        self.assertEqual(ayar["cikti_koku"], "ciktilar/ornek-universitesi")
        k = A.Klasorler(ayar)
        self.assertEqual(k.kok, yollar.REPO / "ciktilar" / "ornek-universitesi")
        self.assertEqual(k.veri, k.harita.parent)   # şablonlar haritanın yanına

    def test_anahtarlar_istenmedikce_kaydedilmez(self):
        A.yeni_profil("a", "https://a.com/", klasor=self.profiller)
        ayar = A.yukle(self.ayar_dosyasi, self.profiller, profil="a")
        ayar.update(anthropic_key="gizli-1", openai_key="gizli-2", ai_modeller="openai:x")
        A.kaydet(ayar, self.ayar_dosyasi, self.profiller)
        metin = self.ayar_dosyasi.read_text(encoding="utf-8")
        self.assertNotIn("gizli", metin)
        self.assertIn("openai:x", metin)
        ayar["anahtarlari_kaydet"] = True
        A.kaydet(ayar, self.ayar_dosyasi, self.profiller)
        self.assertIn("gizli-1", self.ayar_dosyasi.read_text(encoding="utf-8"))

    def test_profil_ve_genel_ayarlar_ayri_dosyalarda(self):
        A.yeni_profil("a", "https://a.com/", klasor=self.profiller)
        ayar = A.yukle(self.ayar_dosyasi, self.profiller, profil="a")
        ayar["esz"] = 7
        ayar["claude_model"] = "claude-test"
        A.kaydet(ayar, self.ayar_dosyasi, self.profiller)
        profil = json.loads((self.profiller / "a.json").read_text(encoding="utf-8"))
        genel = json.loads(self.ayar_dosyasi.read_text(encoding="utf-8"))
        self.assertEqual(profil["esz"], 7)
        self.assertNotIn("claude_model", profil)
        self.assertEqual(genel["claude_model"], "claude-test")
        self.assertNotIn("esz", genel)

    def test_varsayilan_gorunum_sade(self):
        """Windows'ta hızlı olan sade görünüm varsayılandır; eski 'gorunum' anahtarı okunmaz
        (eskiden 'modern' kendiliğinden kaydediliyordu, kullanıcıyı yavaş temada tutmasın)."""
        self.ayar_dosyasi.write_text(json.dumps({"gorunum": "modern"}), encoding="utf-8")
        ayar = A.yukle(self.ayar_dosyasi, self.profiller)
        self.assertEqual(ayar["arayuz_gorunumu"], "sade")
        self.assertNotIn("gorunum", ayar)

    def test_bozuk_tur_yok_sayilir(self):
        self.profiller.mkdir()
        (self.profiller / "b.json").write_text(json.dumps({"esz": "dört", "kesif_rps": 3}), encoding="utf-8")
        ayar = A.yukle(self.ayar_dosyasi, self.profiller, profil="b")
        self.assertEqual(ayar["esz"], A.PROFIL_VARSAYILAN["esz"])
        self.assertEqual(ayar["kesif_rps"], 3.0)   # int, float alana kabul edilir

    def test_hazir_oidb_profili(self):
        ayar = A.yukle(self.ayar_dosyasi, yollar.PROFILLER, profil="meu-oidb")
        k = A.Klasorler(ayar)
        self.assertEqual(k.test, yollar.CIKTILAR / "meu-oidb" / "test_output")
        self.assertEqual(k.temsilciler, yollar.VERI / "meu-oidb" / "template_representatives.json")
        self.assertTrue(k.harita.exists())
        self.assertEqual(harita_url_sayisi(k.harita), 17411)   # ham liste; tester bozukları ayıklar
        self.assertEqual(ayar["site_tanimi"], "a Turkish university website (Mersin Üniversitesi)")


class AdimTestleri(GeciciKlasor):
    def ayar(self, **ek):
        A.yeni_profil("site", "https://site.example/", klasor=self.profiller)
        a = A.yukle(self.ayar_dosyasi, self.profiller, profil="site")
        a.update(ek)
        return a

    def test_her_adim_komut_uretir(self):
        ayar = A.yukle(self.ayar_dosyasi, yollar.PROFILLER, profil="meu-oidb")
        gruplar = {g for g, _ in GRUPLAR}
        for adim in ADIMLAR:
            self.assertIn(adim.grup, gruplar)
            komutlar = adim.komutlar(ayar)
            self.assertTrue(komutlar, adim.id)
            for k in komutlar:
                self.assertTrue(k.argv or k.fonksiyon, adim.id)
                self.assertTrue(all(isinstance(x, str) for x in k.argv), adim.id)

    def test_tam_test_parcalara_bolunur(self):
        harita = self.t / "h.json"
        harita.write_text(json.dumps({"url_list": [f"https://s/{i}" for i in range(4500)]}), encoding="utf-8")
        komutlar = ADIM["tam_test"].komutlar(self.ayar(harita=str(harita), parca=2000, taze_basla=True))
        self.assertEqual(len(komutlar), 3)
        self.assertIn("--fresh", komutlar[0].argv)
        self.assertNotIn("--fresh", komutlar[1].argv)
        self.assertEqual(komutlar[2].argv[komutlar[2].argv.index("--offset") + 1], "4000")

    def test_site_secenekleri_testere_gider(self):
        k = ADIM["deneme"].komutlar(self.ayar(site_adi="Örnek", locale="en-US"))[0]
        self.assertEqual(k.argv[k.argv.index("--site-adi") + 1], "Örnek")
        self.assertEqual(k.argv[k.argv.index("--locale") + 1], "en-US")

    def test_kesif_kurallari(self):
        a = self.ayar(kesif_haric="/arama /etiket/", kesif_tarayici=True, kesif_yoksay_param="")
        argv = ADIM["kesif"].komutlar(a)[1].argv
        self.assertIn("--tarayici", argv)
        i = argv.index("--haric")
        self.assertEqual(argv[i + 1:i + 3], ["/arama", "/etiket/"])
        self.assertIn("--yoksay-param", argv)   # boş liste = hiçbir parametreyi silme

    def test_ai_saglayici_ve_site_tanimi(self):
        a = self.ayar(ai_modeller="openai:gpt-x,gemini", openai_url="http://yerel:1234/v1",
                      openai_key="k", site_tanimi="an online shop", site_dili="German")
        k = ADIM["ai_analiz"].komutlar(a)[0]
        for bayrak, deger in (("--modeller", "openai:gpt-x,gemini"), ("--openai-url", "http://yerel:1234/v1"),
                              ("--site-tanimi", "an online shop"), ("--site-dili", "German")):
            self.assertEqual(k.argv[k.argv.index(bayrak) + 1], deger)
        self.assertEqual(k.env["OPENAI_API_KEY"], "k")

    def test_tiklama_kirik_link_ciktisini_kullanir(self):
        """Tıklama doğrulama site haritasındaki sayfa ayrıntılarına değil, kırık link denetiminin
        çıktısına dayanır (keşif haritalarında ve ÖİDB haritasında sayfa linkleri yok)."""
        ayar = dict(A.VARSAYILAN, cikti_koku=str(self.t))
        k = ADIM["tiklama"].komutlar(ayar)[0].goster()
        self.assertIn("--kirik-linkler", k)
        self.assertIn("broken_links.csv", k)
        self.assertLess(TAM_HAT_SIRA("link"), TAM_HAT_SIRA("tiklama"))

    def test_hakem_bakilamayan_dilimleri_atlamaz(self):
        """Tür örneklemesinde ana modelin bakamadığı dilimler (Gemma kalıcı 500) ayrı turda
        hakeme gider."""
        ayar = dict(A.VARSAYILAN, cikti_koku=str(self.t), ai_hakem_ornek=3, ai_hakem_grup="tur")
        komutlar = [k.goster() for k in ADIM["ai_hakem"].komutlar(ayar)]
        self.assertEqual(len(komutlar), 2)
        self.assertIn("--sadece-bakilamayan", komutlar[1])
        self.assertEqual(len(ADIM["ai_hakem"].komutlar(dict(ayar, ai_hakem_ornek=0))), 1)

    def test_bologna_adresi_ve_modu(self):
        a = self.ayar(bologna_url="https://obs.baska.edu.tr/oibs/bologna/", bologna_mod="yerel")
        komutlar = ADIM["bologna_program"].komutlar(a)
        self.assertEqual(komutlar[0].argv[:2], ["go", "build"])
        argv = komutlar[1].argv
        self.assertEqual(argv[argv.index("--base-url") + 1], "https://obs.baska.edu.tr/oibs/bologna/")
        self.assertIn("BOLOGNA_DB_URL", komutlar[1].env)
        docker = ADIM["bologna_program"].komutlar(self.ayar(bologna_mod="docker"))
        self.assertEqual(docker[0].argv[:2], ["docker", "compose"])

    def test_harita_yoksa_tam_hat_kesifle_baslar(self):
        self.assertEqual(tam_hat(self.ayar(harita=str(self.t / "yok.json")))[0], "kesif")
        harita = self.t / "var.json"
        harita.write_text(json.dumps(["https://s/1"]), encoding="utf-8")
        self.assertEqual(harita_url_sayisi(harita), 1)
        self.assertNotIn("kesif", tam_hat(self.ayar(harita=str(harita))))


class CalistiriciTestleri(GeciciKlasor):
    def ayar(self):
        a = dict(A.VARSAYILAN)
        a["cikti_koku"] = str(self.t)
        return a

    def test_cikti_ve_kayit_dosyasi(self):
        cikti = []
        kod = f"print('satır-1'); import sys; sys.stdout.write('ilerleme 1\\rilerleme 2\\n')"
        adim = Adim("x", "web", "X", "", lambda a: [Komut([sys.executable, "-c", kod])])
        self.assertTrue(Calistirici(cikti.append).calistir([adim], self.ayar()))
        metin = "".join(cikti)
        self.assertIn("satır-1", metin)
        self.assertIn("ilerleme 2", metin)
        kayitlar = list((self.t / "merkez_kayitlari").glob("*_x.log"))
        self.assertEqual(len(kayitlar), 1)
        self.assertIn("satır-1", kayitlar[0].read_text(encoding="utf-8"))

    def test_hata_sonraki_adimi_durdurur(self):
        cikti = []
        hatali = Adim("h", "web", "H", "", lambda a: [Komut([sys.executable, "-c", "raise SystemExit(3)"])])
        sonraki = Adim("s", "web", "S", "", lambda a: [Komut([sys.executable, "-c", "print('ikinci')"])])
        self.assertFalse(Calistirici(cikti.append).calistir([hatali, sonraki], self.ayar()))
        self.assertNotIn("ikinci\n", "".join(cikti))
        cikti.clear()
        Calistirici(cikti.append).calistir([hatali, sonraki], self.ayar(), devam_et=True)
        self.assertIn("ikinci\n", "".join(cikti))

    def test_olmayan_program(self):
        cikti = []
        adim = Adim("y", "web", "Y", "", lambda a: [Komut(["boyle-bir-program-yok-123"])])
        self.assertFalse(Calistirici(cikti.append).calistir([adim], self.ayar()))
        self.assertIn("Program bulunamadı", "".join(cikti))

    @unittest.skipIf(os.name == "nt", "POSIX süreç grubu testi")
    def test_durdurma_alt_surecleri_de_kapatir(self):
        uzun = "sl" + "eep 47"
        adim = Adim("u", "web", "U", "", lambda a: [Komut(["sh", "-c", f"{uzun} & {uzun}"])])
        c = Calistirici(lambda m: None)
        sonuc = []
        t = threading.Thread(target=lambda: sonuc.append(c.calistir([adim], self.ayar())))
        t.start()
        time.sleep(1)
        c.durdur()
        t.join(15)
        self.assertFalse(t.is_alive())
        self.assertEqual(sonuc, [False])
        kalan = subprocess.run(["pgrep", "-f", uzun], capture_output=True, text=True).stdout.strip()
        self.assertEqual(kalan, "")


class KesifKuralTestleri(unittest.TestCase):
    def kurallar(self, **ek):
        import kesif
        a = kesif.parse_args(["--url", "https://site.example/"])
        for k, v in ek.items():
            setattr(a, k, v)
        return kesif.Kurallar(a)

    def test_normallestirme(self):
        k = self.kurallar()
        n = lambda u: k.normallestir(u, "https://site.example/a/")  # noqa: E731
        self.assertEqual(n("b.html?utm_source=x&id=2#ust"), ("https://site.example/a/b.html?id=2", "sayfa"))
        self.assertEqual(n("/belge.PDF"), ("https://site.example/belge.PDF", "belge"))
        self.assertEqual(n("https://baska.com/")[1], "dis")
        self.assertEqual(n("mailto:a@b.c")[1], "sema")
        self.assertEqual(n("/logo.png")[1], "dosya")

    def test_haric_ve_sorgu_limiti(self):
        import re
        k = self.kurallar(sorgu_limiti=2)
        k.haric = [re.compile("/arama")]
        self.assertEqual(k.normallestir("/arama?q=1", "https://site.example/")[1], "haric")
        izin = [k.sorgu_izinli(f"https://site.example/liste?s={i}") for i in range(4)]
        self.assertEqual(izin, [True, True, False, False])


class AnalizTestleri(unittest.TestCase):
    def test_varsayilan_talimat_degismedi(self):
        """Site tanımı parametreli oldu; ÖİDB için talimat eskisiyle birebir aynı kalmalı
        (önceki AI sonuçlarıyla karşılaştırılabilirlik)."""
        kaynak = (yollar.GORSEL_DENETIM / "analiz.py").read_text(encoding="utf-8")
        ns = {}
        bas = kaynak.index("SITE_TANIMI =")
        son = kaynak.index("TALIMAT = TALIMAT_SABLONU.format")
        exec(kaynak[bas:son], ns)
        talimat = ns["TALIMAT_SABLONU"].format(site=ns["SITE_TANIMI"], dil=ns["SITE_DILI"])
        self.assertTrue(talimat.startswith(
            "You are a meticulous UI QA reviewer for a Turkish university website (Mersin Üniversitesi)."))
        self.assertIn("instead of Turkish letters", talimat)
        self.assertIn("- Turkish text is expected and correct.", talimat)

    def _analiz_hazirla(self, sayi=20):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("pillow yok")
        sys.path.insert(0, str(yollar.GORSEL_DENETIM))
        import analiz
        from PIL import Image
        d = Path(tempfile.mkdtemp())
        ornekler = []
        for k in range(sayi):
            p = d / f"s{k}.png"
            Image.new("RGB", (400, 300), "white").save(p)
            ornekler.append({"dosya": p.name, "tam_yol": p, "cihaz": "desktop", "sayfa": "u",
                             "sablon": "x"})
        return analiz, d, ornekler

    @staticmethod
    def _sahte(bozuk):
        """bozuk(n): n. çağrı zaman aşımına uğrasın mı."""
        class Sahte:
            ad, kapali, n = "gemini:sahte", False, 0

            def sor(self, png, baglam):
                Sahte.n += 1
                if bozuk(Sahte.n):
                    raise TimeoutError("The read operation timed out")
                return {"defects": []}, {"girdi": 1, "cikti": 1}, ""

            def hata_tekrar_denenir_mi(self, e):
                return False
        return Sahte()

    def test_ilerleme_basarili_sayisi_ve_zaman_asimi(self):
        """İlerleme satırı başarılı/yapılamayan sayısını gösterir; asılı bağlantı hata sayılır."""
        import contextlib, io, types
        analiz, d, ornekler = self._analiz_hazirla()
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            _, sayac = analiz.calistir(types.SimpleNamespace(dilim=3, toplu=False, paralel=1),
                                       ornekler, d, [self._sahte(lambda n: n % 4 == 0)])
        self.assertIn("[20/20] ✓ 15 başarılı  ✗ 5 yapılamadı", cikti.getvalue())
        self.assertEqual(sayac, {"zaman aşımı (cevap gelmedi)": 5})
        self.assertTrue(analiz.zaman_asimi_mi(TimeoutError("x")))

    def test_ilk_model_yapilamayanlari_ayni_calistirmada_yeniden_dener(self):
        import contextlib, io, types
        analiz, d, ornekler = self._analiz_hazirla()
        a = types.SimpleNamespace(dilim=3, toplu=False, paralel=1, tekrar_tur=2)
        ist = self._sahte(lambda n: n <= 20 and n % 4 == 0)   # yalnız ilk turda 5 hata
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            analiz.turlarla_calistir(a, ornekler, d, [ist])
            k = analiz.kapsam(ornekler, d, ist.ad, 3)
            analiz.yapilamayan_ozeti(k, 2)
        self.assertIn("Yeniden deneme turu 1/2: 5 yapılamayan", cikti.getvalue())
        self.assertNotIn("turu 2/2", cikti.getvalue())
        self.assertEqual((k["beklenen"], k["tamam"], k["yapilamadi"], k["denenmedi"]), (20, 20, 0, 0))
        self.assertIn("hepsi tamamlandı", cikti.getvalue())

    def test_hakem_ilk_model_bitmeden_baslamaz(self):
        """Yarıda kalan (hiç denenmemiş dilimi olan) ilk modelden sonra hakem çalışmaz;
        denemelere rağmen yapılamayanlar ise hakeme gider."""
        import contextlib, io, types
        analiz, d, ornekler = self._analiz_hazirla()
        a = types.SimpleNamespace(dilim=3, toplu=False, paralel=1, tekrar_tur=0, zorla=False,
                                  modeller="gemini:sahte", claude_model="c", gemini_model="g")
        with contextlib.redirect_stdout(io.StringIO()):
            analiz.calistir(a, ornekler[:10], d, [self._sahte(lambda n: n == 3)])
            self.assertFalse(analiz.ilk_model_tamam_mi(a, ornekler, d, "gemini:hakem"))
            analiz.calistir(a, ornekler, d, [self._sahte(lambda n: False)])
            self.assertTrue(analiz.ilk_model_tamam_mi(a, ornekler, d, "gemini:hakem"))
        k = analiz.kapsam(ornekler, d, "gemini:sahte", 3)
        self.assertEqual((k["tamam"], k["denenmedi"]), (20, 0))
        # hata türünden bağımsız: zaman aşımı alan ve hiç başarısı olmayan dilim hakeme gider
        with open(d / "sonuclar.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"model": "gemini:sahte", "dosya": "yok.png", "dilim": 1,
                                "sablon": "x", "cihaz": "desktop", "cevap": None,
                                "hata": "TimeoutError: timed out"}) + "\n")
        self.assertIn(("yok.png", 1), analiz.hakem_dilimleri(d, "gemini:hakem"))


if __name__ == "__main__":
    unittest.main()


class IzlemeTestleri(unittest.TestCase):
    def test_ilerleme_bicimleri(self):
        from merkez.izleme import ilerleme_oku
        self.assertEqual(ilerleme_oku("  [12/2000] PASS  200  https://x"), (12, 2000))
        self.assertEqual(ilerleme_oku("    120/900 (3 kırık)"), (120, 900))
        self.assertEqual(ilerleme_oku("    450 sayfa | kuyruk 1550 | belge 3 | hata 0"), (450, 2000))
        self.assertEqual(ilerleme_oku('time=x level=INFO msg=ilerleme biten=12 toplam=442 ders=3'), (12, 442))
        self.assertEqual(ilerleme_oku("msg=\"havuz ilerleme\" biten_kod=5 toplam_kod=50"), (5, 50))
        self.assertIsNone(ilerleme_oku("Tarih 2026/10/05"))
        self.assertIsNone(ilerleme_oku("[5/0] bozuk"))

    def test_sorun_siniflandirma(self):
        from merkez.izleme import sorun_turu
        self.assertEqual(sorun_turu("Traceback (most recent call last):"), "hata")
        self.assertEqual(sorun_turu("FileNotFoundError: [Errno 2] yok"), "hata")
        self.assertEqual(sorun_turu("[HATA] Link kaynağı bulunamadı"), "hata")
        self.assertEqual(sorun_turu("time=x level=ERROR msg=istek"), "hata")
        self.assertEqual(sorun_turu("[!] robots.txt okunamadı"), "uyari")
        self.assertEqual(sorun_turu("  [3/10] ERROR None  https://x (zaman aşımı)"), "uyari")
        self.assertEqual(sorun_turu("time=x level=WARN msg=503"), "uyari")
        # olağan çıktılar sorun sayılmaz
        for satir in ("  [3/10] FAIL  404  https://x", "    450 sayfa | kuyruk 3 | hata 0",
                      "ilerleme biten=1 toplam=2 hata=0", "Kırık link     : 12",
                      "1) HATA TÜRÜ BAŞINA İSABET (hakem aynı dilimde aynı türü buldu mu?)", ""):
            self.assertIsNone(sorun_turu(satir), satir)

    def test_satir_bolucu_ve_sure(self):
        from merkez.izleme import SatirBolucu, SureTahmini, sure_metni
        b = SatirBolucu()
        self.assertEqual(b.ekle("a\nb"), ["a"])
        self.assertEqual(b.ekle("c\rd\r\n"), ["bc", "d"])
        self.assertEqual(b.bitir(), [])
        saat = [0.0]
        t = SureTahmini(simdi=lambda: saat[0])
        t.ekle(0.2)
        saat[0] = 10.0
        t.ekle(0.4)          # 10 sn'de %20 ilerledi -> kalan %60 için 30 sn
        self.assertAlmostEqual(t.kalan(), 30.0)
        self.assertEqual(sure_metni(3725), "1 sa 02 dk")
        self.assertEqual(sure_metni(None), "hesaplanıyor")

    def test_sirasiz_ilerleme_geri_gitmez(self):
        """Eşzamanlı araçlar [i/n]'yi sırasız basabilir; yüzde geri gitmemeli."""
        olaylar = []
        kod = "for i in (1, 3, 2, 5, 4, 6):\n    print(f'  [{i}/6] PASS', flush=True)"
        with tempfile.TemporaryDirectory() as t:
            ayar = dict(A.VARSAYILAN, cikti_koku=t)
            adim = Adim("x", "web", "X", "", lambda a: [Komut([sys.executable, "-c", kod])])
            Calistirici(lambda m: None, olaylar.append).calistir([adim], ayar)
        ilerleme = [o for o in olaylar if o["tur"] == "ilerleme" and o["biten"] is not None]
        self.assertEqual([o["biten"] for o in ilerleme], [1, 3, 3, 5, 5, 6])
        oranlar = [o["oran_adim"] for o in olaylar if o["tur"] == "ilerleme"]
        self.assertEqual(oranlar, sorted(oranlar))

    def test_devam_eden_aracin_ilk_satiri_hiz_sayilmaz(self):
        """'[5/10]' ile başlayan (yarısı önceden yapılmış) araçta ilk yarı hıza katılmaz."""
        kod = "for i in (5, 6, 7):\n    print(f'  [{i}/10] PASS', flush=True)"
        with tempfile.TemporaryDirectory() as t:
            ayar = dict(A.VARSAYILAN, cikti_koku=t)
            adim = Adim("x", "web", "X", "", lambda a: [Komut([sys.executable, "-c", kod])])
            c = Calistirici(lambda m: None, lambda o: None)
            c.calistir([adim], ayar)
        self.assertAlmostEqual(c.tahmin.son, 0.7)
        self.assertAlmostEqual(c.tahmin.islenen, 0.2)     # yalnız 5 -> 7 çalışılarak yapıldı

    def test_sure_tahmini_atlama_ve_pencere(self):
        from merkez.izleme import SureTahmini
        saat = [0.0]
        t = SureTahmini(simdi=lambda: saat[0])
        t.ekle(0.0)
        saat[0] = 1.0
        t.ekle(0.5, atlama=True)     # zaten yapılmış parça: anında geçti, hız sayılmaz
        saat[0] = 11.0
        t.ekle(0.6)                  # 11 sn'de gerçekten %10 -> kalan %40 için 44 sn
        self.assertAlmostEqual(t.kalan(), 44.0)
        t.ekle(0.55)                 # geri giden oran yok sayılır
        self.assertAlmostEqual(t.son, 0.6)

        t = SureTahmini(simdi=lambda: saat[0], pencere=100)
        saat[0] = 0.0
        t.ekle(0.0)
        saat[0] = 50.0
        t.ekle(0.5)                  # başta hızlı ...
        for sn in range(60, 260, 10):
            saat[0] = float(sn)
            t.ekle(0.5 + (sn - 50) * 0.0005)   # ... sonra 10 sn'de %0,5
        # son 100 sn'ye göre: 0,0005/sn -> kalan (1-0,6)/0,0005 = 800 sn (baştaki hız değil)
        self.assertAlmostEqual(t.kalan(), 800.0, delta=60)

    def test_calistirici_olaylari(self):
        olaylar = []
        kod = ("for i in range(1, 5):\n    print(f'  [{i}/4] PASS', flush=True)\n"
               "print('[!] dikkat')\nprint('ValueError: bozuk')")
        with tempfile.TemporaryDirectory() as t:
            ayar = dict(A.VARSAYILAN, cikti_koku=t)
            adim = Adim("x", "web", "X", "", lambda a: [Komut([sys.executable, "-c", kod])])
            Calistirici(lambda m: None, olaylar.append).calistir([adim], ayar)
        turler = [o["tur"] for o in olaylar]
        self.assertEqual(turler[0], "basladi")
        self.assertEqual(turler[-1], "bitti")
        ilerleme = [o for o in olaylar if o["tur"] == "ilerleme" and o["biten"]]
        self.assertEqual([o["biten"] for o in ilerleme], [1, 2, 3, 4])
        self.assertAlmostEqual(ilerleme[-1]["oran_adim"], 1.0)
        sorunlar = [(o["seviye"], o["satir"]) for o in olaylar if o["tur"] == "sorun"]
        self.assertIn(("uyari", "[!] dikkat"), sorunlar)
        self.assertIn(("hata", "ValueError: bozuk"), sorunlar)
        son = olaylar[-1]["sonuclar"][0]
        self.assertEqual((son["hata"], son["uyari"], son["sonuc"]), (1, 1, "basarili"))
        self.assertTrue(son["kayit"].endswith("_x.log"))

    def test_cok_parcali_adimda_oran(self):
        olaylar = []
        komutlar = [Komut([sys.executable, "-c", "print('  [1/2] a'); print('  [2/2] b')"]) for _ in range(2)]
        with tempfile.TemporaryDirectory() as t:
            adim = Adim("p", "web", "P", "", lambda a: komutlar)
            Calistirici(lambda m: None, olaylar.append).calistir([adim], dict(A.VARSAYILAN, cikti_koku=t))
        oranlar = [round(o["oran_adim"], 2) for o in olaylar if o["tur"] == "ilerleme" and o["biten"]]
        self.assertEqual(oranlar, [0.25, 0.5, 0.75, 1.0])


class ModelVarsayilanTestleri(unittest.TestCase):
    def test_gorsel_denetimde_kullanilan_modeller_varsayilan(self):
        """Program, görsel denetimde fiilen kullanılan modellerle açılmalı: rapor.py ve isabet.py
        varsayılanları (ana Gemma 4, hakem Gemini Flash Lite) ve yerel modelde qwen2.5vl:3b."""
        import re
        kaynak = lambda ad: (yollar.ARACLAR / ad).read_text(encoding="utf-8")  # noqa: E731
        varsayilan = lambda metin, bayrak: re.search(  # noqa: E731
            rf'"{bayrak}", default="([^"]+)"', metin).group(1)
        isabet, rapor = kaynak("visual_audit/isabet.py"), kaynak("visual_audit/rapor.py")
        analiz = kaynak("visual_audit/analiz.py")
        V = A.VARSAYILAN
        self.assertEqual(V["ai_ana"], varsayilan(rapor, "--ana"))
        self.assertEqual(V["ai_ana"], varsayilan(isabet, "--ana"))
        self.assertEqual(V["ai_modeller"], V["ai_ana"])
        self.assertEqual(V["ai_modeller"], varsayilan(analiz, "--modeller"))
        self.assertEqual(V["ai_hakem"], varsayilan(isabet, "--hakem"))
        self.assertEqual(V["ai_isabet_hakem"], V["ai_hakem"])
        self.assertEqual(V["ollama_model"], varsayilan(kaynak("visual_ai_review.py"), "--model"))


class AnaSayfaTestleri(GeciciKlasor):
    def test_yol_haritasi_ve_kutucuklar(self):
        from merkez.durum import kutucuklar, yol_haritasi
        harita = self.t / "h.json"
        harita.write_text(json.dumps({"url_list": ["https://s/1", "https://s/2"]}), encoding="utf-8")
        ayar = dict(A.VARSAYILAN, cikti_koku=str(self.t / "cikti"), harita=str(harita))
        yh = yol_haritasi(ayar)
        self.assertEqual([r[0] for r in yh][:3], ["Site haritası", "Deneme testi", "Tüm site testi"])
        self.assertTrue(yh[0][2])                       # harita var: 1. aşama tamam
        self.assertFalse(yh[1][2])                      # test yok
        self.assertEqual(yh[1][4], ["deneme"])          # sıradaki aşamanın çalıştıracağı adım
        test = self.t / "cikti" / "test_output"
        test.mkdir(parents=True)
        (test / "results.jsonl").write_text(
            json.dumps({"url": "https://s/1", "http_status": 200}) + "\n" +
            json.dumps({"url": "https://s/2", "http_status": 404}) + "\n", encoding="utf-8")
        (test / "report.html").write_text("x", encoding="utf-8")
        yh = yol_haritasi(ayar)
        self.assertTrue(yh[1][2] and yh[2][2])          # tüm site testi deneme aşamasını da karşılar
        kutu = {b: (d, alt) for b, d, alt, _ in kutucuklar(ayar)}
        self.assertEqual(kutu["Site haritası"][0], "2")
        self.assertEqual(kutu["Test edilen"][0], "2")
        self.assertEqual(kutu["Kırık sayfa"][0], "1")

    def test_ilk_model_ve_hakem_ayri_asamalar(self):
        """Ana sayfada ilk model ve hakem ayrı satır/düğme; ilk model kapsamı kapsam.json'dan."""
        from merkez.ayarlar import Klasorler
        from merkez.durum import yol_haritasi
        ayar = dict(A.VARSAYILAN, cikti_koku=str(self.t / "cikti"), harita=str(self.t / "yok.json"))
        satirlar = {r[0]: r for r in yol_haritasi(ayar)}
        ilk, hakem = satirlar["Yapay zekâ: ilk model"], satirlar["Yapay zekâ: hakem ve rapor"]
        self.assertEqual(ilk[4], ["ai_analiz"])
        self.assertEqual(hakem[4][0], "ai_hakem")
        self.assertFalse(ilk[2])
        ai = Klasorler(ayar).ai_sonuc
        ai.mkdir(parents=True)
        m = {"model": "gemini:g", "beklenen": 100, "tamam": 60, "yapilamadi": 5, "kota": 0,
             "denenmedi": 35, "turler": {}}
        (ai / "kapsam.json").write_text(json.dumps({"ilk_model": {"modeller": [m]}}), encoding="utf-8")
        ilk = {r[0]: r for r in yol_haritasi(ayar)}["Yapay zekâ: ilk model"]
        self.assertFalse(ilk[2])
        self.assertEqual(ilk[3], "60/100 dilim, 5 yapılamadı, 35 denenmedi")
        m.update(tamam=95, denenmedi=0)
        (ai / "kapsam.json").write_text(json.dumps({"ilk_model": {"modeller": [m]}}), encoding="utf-8")
        ilk = {r[0]: r for r in yol_haritasi(ayar)}["Yapay zekâ: ilk model"]
        self.assertTrue(ilk[2])                          # yapılamayan 5 dilim hakeme gider


class SozlesmeTestleri(unittest.TestCase):
    """Programın araçlara gönderdiği her seçenek, aracın kodunda tanımlı olmalı. Araçlar
    (ör. görsel denetim) güncellendiğinde programla uyumsuzluk burada yakalanır."""

    def ayarlar(self):
        a = A.yukle(Path(tempfile.gettempdir()) / "yok.json", yollar.PROFILLER, profil="meu-oidb")
        # isteğe bağlı seçeneklerin hepsi komutlara girsin
        a.update(ai_limit=5, ai_dakika_limit=8, ai_hakem_ornek=3, ai_toplu=True, claude_effort="high",
                 rota_limit=10, tablet=True, gorunur=True, taze_basla=True, kesif_tarayici=True,
                 kesif_robots=True, kesif_alt_alanlar=True, kesif_haric="/a", kesif_dahil="/b",
                 bologna_yillar="3", ayrintili=True)
        return a

    def test_python_araclari(self):
        import re
        eksikler = []
        for mod in ("docker", "yerel"):
            ayar = self.ayarlar()
            ayar["bologna_mod"] = mod
            for adim in ADIMLAR:
                for k in adim.komutlar(ayar):
                    betik = next((x for x in k.argv if x.endswith(".py")), None)
                    if not betik:
                        continue
                    kaynak_yolu = Path(betik) if Path(betik).is_absolute() else Path(k.cwd) / betik
                    kaynak = kaynak_yolu.read_text(encoding="utf-8")
                    for arg in k.argv:
                        if re.fullmatch(r"--[a-z][a-z0-9-]*", arg) and f'"{arg}"' not in kaynak:
                            eksikler.append(f"{adim.id}: {kaynak_yolu.name} {arg}")
        self.assertEqual(sorted(set(eksikler)), [])

    def test_bologna_cli(self):
        import re
        kaynak = (yollar.BOLOGNA / "internal" / "cli" / "cli.go").read_text(encoding="utf-8")
        eksikler = []
        for mod in ("docker", "yerel"):
            ayar = self.ayarlar()
            ayar["bologna_mod"] = mod
            for adim in ADIMLAR:
                if adim.grup != "bologna":
                    continue
                for k in adim.komutlar(ayar):
                    for arg in k.argv:
                        m = re.fullmatch(r"--([a-z][a-z0-9-]*)", arg)
                        if m and k.argv[0] != "go" and f'"{m.group(1)}"' not in kaynak \
                                and m.group(1) != "profile" and m.group(1) != "rm":
                            eksikler.append(f"{adim.id}: --{m.group(1)}")
        self.assertEqual(sorted(set(eksikler)), [])


class SatirSonuTestleri(unittest.TestCase):
    def test_windows_satir_sonu_ve_bolunmus_crlf(self):
        cikti = []
        c = Calistirici(cikti.append)
        c._izleme_sifirla()
        for parca in ("bir\r\niki\r", "\nilerleme 1\rilerleme 2\r\n", "son\r"):
            c._cikti(parca)
        c._cikti("", son=True)
        self.assertEqual("".join(cikti), "bir\niki\nilerleme 1\rilerleme 2\nson\r")


class DurdurmaTestleri(GeciciKlasor):
    def test_durdurma_her_sistemde(self):
        """Windows'ta Ctrl+Break/taskkill, diğerlerinde SIGINT/SIGKILL yolu."""
        adim = Adim("u", "web", "U", "", lambda a: [
            Komut([sys.executable, "-c", "import time\nprint('basladi', flush=True)\ntime.sleep(120)"])])
        c = Calistirici(lambda m: None)
        sonuc = []
        t = threading.Thread(target=lambda: sonuc.append(
            c.calistir([adim], dict(A.VARSAYILAN, cikti_koku=str(self.t)))))
        t.start()
        time.sleep(2)
        bas = time.time()
        c.durdur()
        t.join(30)
        self.assertFalse(t.is_alive(), "durdurulan süreç kapanmadı")
        self.assertLess(time.time() - bas, 20)
        self.assertEqual(sonuc, [False])


class OnbellekTestleri(GeciciKlasor):
    """Arayüz durum dosyalarını önbellekten okur; dosya değişince yeniden okunmalı."""

    def test_dosya_degisince_yeniden_okunur(self):
        from merkez.durum import _jsonl
        yol = self.t / "results.jsonl"
        yol.write_text(json.dumps({"url": "a", "overall": "pass", "http_status": 200}) + "\n", encoding="utf-8")
        self.assertEqual(len(_jsonl(yol)), 1)
        self.assertIs(_jsonl(yol), _jsonl(yol))        # değişmedi: aynı nesne, yeniden okunmadı
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": "b", "overall": "fail", "http_status": 404,
                                "js_errors": ["x"], "evidence": {"html": "uzun"}}) + "\n")
        kayitlar = _jsonl(yol)
        self.assertEqual(len(kayitlar), 2)
        self.assertTrue(kayitlar[1]["js_errors"])
        self.assertNotIn("evidence", kayitlar[1])      # önbellekte yalnız özet alanları

    def test_harita_sayisi_guncellenir(self):
        yol = self.t / "harita.json"
        yol.write_text(json.dumps({"url_list": ["a", "b"]}), encoding="utf-8")
        self.assertEqual(harita_url_sayisi(yol), 2)
        yol.write_text(json.dumps({"url_list": ["a", "b", "c"]}), encoding="utf-8")
        self.assertEqual(harita_url_sayisi(yol), 3)
        self.assertEqual(harita_url_sayisi(self.t / "yok.json"), 0)


def _ekran_var():
    try:
        import tkinter
        k = tkinter.Tk()
        k.destroy()
        return True
    except Exception:       # tkinter yok ya da ekran yok (Linux CI)
        return False


@unittest.skipUnless(_ekran_var(), "ekran/tkinter yok")
class ArayuzTestleri(GeciciKlasor):
    """Pencere açılır, sayfalar arasında geçilir, boyut değişir (Windows'ta çizim dondurma dahil)."""

    def test_sayfa_gecisi_ve_boyutlandirma(self):
        import tkinter as tk
        from merkez import arayuz
        ayar = A.yukle(self.ayar_dosyasi, self.profiller)
        ayar["cikti_koku"] = str(self.t / "cikti")
        kok = tk.Tk()
        hatalar = []
        kok.report_callback_exception = lambda *a: hatalar.append(a[1])
        try:
            app = arayuz.Uygulama(kok, ayar)
            kok.update()
            self.assertEqual(kok.state(), "normal")
            for ad in list(app.sayfalar) + ["ana", "ayarlar", "web"]:
                app._sayfa_ac(ad)
                kok.update()
                self.assertEqual(app.etkin_sayfa, ad)
                # öndeki sayfa içerik alanını kaplar, arkadakiler sabit boyutta bekler
                self.assertEqual(float(app.sayfalar[ad].place_info()["relwidth"]), 1.0)
                self.assertTrue(all(float(s.place_info()["relwidth"]) == 0
                                    for a, s in app.sayfalar.items() if a != ad))
            for g in ("1100x760", "1400x900"):
                kok.geometry(g)
                kok.update()
            self.assertEqual(app.sayfalar["web"].winfo_width(), app.icerik.winfo_width())
            self.assertFalse(any(arayuz._CizimiDondur.derinlik.values()))
        finally:
            kok.destroy()
        self.assertEqual(hatalar, [])


class DenetimRaporuTestleri(GeciciKlasor):
    """Kırık link / belge CSV'lerinden okunabilir rapor."""

    def test_link_ve_belge_raporu(self):
        from merkez import denetim_raporu as D
        ayar = dict(A.VARSAYILAN, cikti_koku=str(self.t / "c"), site_url="https://ornek.edu.tr/",
                    site_adi="Örnek")
        k = A.Klasorler(ayar)
        k.link.mkdir(parents=True)
        k.belge.mkdir(parents=True)
        (k.link / "broken_links.csv").write_text(
            "url,status,kaynak_sayfa,buton_metni\n"
            "https://ornek.edu.tr/yok,404,https://ornek.edu.tr/,Duyurular\n"
            "https://dis.gov.tr/a,error: getaddrinfo ENOTFOUND dis.gov.tr,https://ornek.edu.tr/b,Mevzuat\n"
            "https://ornek.edu.tr/yok,404,https://ornek.edu.tr/,Duyurular\n",   # yeniden çalıştırma tekrarı
            encoding="utf-8")
        (k.belge / "documents_audit.csv").write_text(
            "url,status,content_type,size,source,flag,kaynak_sayfa,buton_metni\n"
            "https://ornek.edu.tr/a.pdf,200,application/pdf,10,dom,erisilebilir,https://ornek.edu.tr/,A\n"
            "https://ornek.edu.tr/b.pdf,404,text/html,,dom,KIRIK/ERISILEMIYOR,https://ornek.edu.tr/,B\n"
            "file:///C:/Users/x/c.docx,file:,,,dom(file:),SIZDIRILMIS YEREL DOSYA YOLU (kirik + bilgi sizintisi),"
            "https://ornek.edu.tr/,Ç\n", encoding="utf-8")
        h = D.link_raporu_yolu(ayar)
        metin = h.read_text(encoding="utf-8")
        self.assertIn("404 Bulunamadı", metin)
        self.assertIn("Alan adı bulunamadı (DNS)", metin)
        self.assertEqual(metin.count('data-sorunlu="1"'), 2)          # tekrar sayılmadı
        excel = (k.link / "kirik_linkler_excel.csv").read_bytes()
        self.assertTrue(excel.startswith(b"\xef\xbb\xbf"))           # BOM: Excel Türkçe'yi doğru açar
        self.assertIn("Site içi".encode(), excel)
        b = D.belge_raporu_yolu(ayar).read_text(encoding="utf-8")
        self.assertIn("Sızdırılmış yerel dosya yolu", b)
        self.assertEqual(b.count('data-sorunlu="1"'), 2)
        self.assertEqual(b.count('data-sorunlu="0"'), 1)
        # durum özeti sorunlu belgeyi ayrı sayar
        from merkez.durum import kutucuklar
        self.assertIn(("Sorunlu belge", "2", "3 belgeden", "hata"), kutucuklar(ayar))


class AdimRaporuTestleri(GeciciKlasor):
    """Her adım, ne üretirse üretsin, bir adım raporu bırakır."""

    def test_her_adim_rapor_birakir(self):
        from merkez.adim_raporu import son_rapor
        ayar = dict(A.VARSAYILAN, cikti_koku=str(self.t / "c"))
        csv_yolu = self.t / "c" / "sonuc.csv"
        kod = (f"import pathlib; p=pathlib.Path(r'{csv_yolu}'); p.parent.mkdir(parents=True, exist_ok=True); "
               "p.write_text('url;karar\\nhttps://a;KIRIK\\n', encoding='utf-8-sig'); print('[HATA] örnek')")
        dosyali = Adim("dosyali", "web", "Dosyalı adım", "açıklama",
                       lambda a: [Komut([sys.executable, "-c", kod])], lambda a: [csv_yolu])
        dosyasiz = Adim("dosyasiz", "web", "Dosyasız adım", "",
                        lambda a: [Komut([sys.executable, "-c", "print('merhaba')"])])
        c = Calistirici(lambda m: None, lambda o: None)
        c.calistir([dosyali, dosyasiz], dict(ayar, hata_olursa_devam=True))
        klasor = A.Klasorler(ayar).adim_raporlari
        self.assertTrue(all(r["rapor"] for r in c.sonuclar))
        r1 = son_rapor(klasor, "dosyali").read_text(encoding="utf-8")
        self.assertIn("<td>KIRIK</td>", r1)                 # CSV önizlemesi
        self.assertIn("[HATA] örnek", r1)                    # hata listesi
        r2 = son_rapor(klasor, "dosyasiz").read_text(encoding="utf-8")
        self.assertIn("merhaba", r2)                         # dosya yoksa çalışma kaydı
        dizin = (klasor / "index.html").read_text(encoding="utf-8")
        self.assertIn("Dosyalı adım", dizin)
        self.assertIn("Dosyasız adım", dizin)
