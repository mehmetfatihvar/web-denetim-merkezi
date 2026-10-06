"""Kılavuzdaki arayüz ekran görüntülerini programın gerçek çalışmasından çeker.

Örnek site http://127.0.0.1:8765/ adresinde yayında olmalı (bkz. cek.sh). Kullanım:
  python arayuz_goruntuleri.py IMG_KLASORU ARAC_PYTHON [uyari]
ARAC_PYTHON araçları çalıştıracak (playwright kurulu) Python'dur. 'uyari' verilirse yalnız
kurulum uyarısı görüntüsü çekilir (ARAC_PYTHON olarak paketleri eksik bir Python verilir).
Görüntüler 1320x900 ekranın tamamından alınır (Xvfb + ImageMagick 'import').
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import tkinter as tk  # noqa: E402
from merkez import ayarlar as A, arayuz  # noqa: E402

IMG, PY = Path(sys.argv[1]), sys.argv[2]
SADECE_UYARI = len(sys.argv) > 3 and sys.argv[3] == "uyari"
kimlik = A.yeni_profil("Örnek Üniversite", "http://127.0.0.1:8765/", "Örnek Üniversite")
ayar = A.yukle(profil=kimlik)
ayar.update(python=PY, kesif_rps=0.0, kesif_sitemap=False, esz=2, zaman_asimi=10, tema="light")
A.kaydet(ayar)
kok = tk.Tk()
app = arayuz.Uygulama(kok, ayar)
arayuz.messagebox.askyesno = lambda *a, **k: True
arayuz.messagebox.showinfo = lambda *a, **k: None


def cek(ad):
    kok.update(); time.sleep(0.5); kok.update()
    subprocess.run(["import", "-window", "root", str(IMG / f"{ad}.png")], check=True)


plan, cekildi = [], set()


def sirada():
    if app.calistirici.calisiyor or (app.is_parcacigi and app.is_parcacigi.is_alive()):
        kok.after(300, sirada); return
    if not plan:
        kok.destroy(); return
    plan.pop(0)()
    kok.after(1500, sirada)


def izle():
    o = app.son_ilerleme
    if o and o["id"] == "tam_test" and o["oran_adim"] > 0.4 and "calisirken" not in cekildi:
        cekildi.add("calisirken"); cek("05_calisirken")
    if app.is_parcacigi and app.is_parcacigi.is_alive():
        kok.after(200, izle)


def ilk():
    app._sayfa_ac("web")
    for i in ("kesif", "tam_test", "belge", "link", "kumeleme", "gorsel", "rota", "teslim"):
        app._sec_degistir(app.listeler[arayuz.ADIM[i].grup], i)
    cek("04_secim")
    app._secilenleri_calistir(); kok.after(300, izle)


def sonra():
    cek("06_son_calisma")
    app._sayfa_ac("ana"); cek("02_ana_sayfa")
    t = app.listeler["web"]; app._sayfa_ac("web"); t.selection_set("tam_test"); t.focus("tam_test")
    app._ayrinti_goster("web"); cek("03_adim_sayfasi")
    t = app.listeler["duzeltme"]; app._sayfa_ac("duzeltme"); t.selection_set("gd_oto"); t.focus("gd_oto")
    app._ayrinti_goster("duzeltme"); cek("10_dogrula_duzelt")
    app._sayfa_ac("ai"); cek("09_yapay_zeka")
    app._sayfa_ac("raporlar"); app._durumu_yenile(); kok.after(800); cek("11_raporlar")
    app._sayfa_ac("ayarlar"); cek("12_ayarlar_site")
    nb = [w for w in app.sayfalar["ayarlar"].winfo_children() if isinstance(w, arayuz.ttk.Notebook)][0]
    nb.select(1); cek("13_ayarlar_genel"); nb.select(0)
    app._sayfa_ac("ana")
    app._baslat(["ai_isabet"])        # veri yokken çalışır ve hata verir: hata sekmesi için


def son():
    app.alt_defter.select(app.sorun_sekmesi); cek("07_hatalar")
    app._yeni_site(); kok.update(); time.sleep(0.5)
    pencere = [w for w in kok.winfo_children() if isinstance(w, tk.Toplevel)][0]
    kok.update(); subprocess.run(["import", "-window", "root", str(IMG / "14_yeni_site.png")], check=True)
    pencere.destroy()
    app.tema_var.set(True); app._tema_degistir(); app._sayfa_ac("ana"); kok.after(800); cek("15_karanlik_tema")
    app.tema_var.set(False); app._tema_degistir()


def uyari():
    app._sayfa_ac("ana"); cek("16_kurulum_uyarisi")


plan += [uyari] if SADECE_UYARI else [ilk, sonra, son]
kok.after(4000 if SADECE_UYARI else 1500, sirada)
kok.mainloop()
print("TAMAM", kimlik)
