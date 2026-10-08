#!/usr/bin/env python3
"""
Web Denetim Merkezi — web sitesi test ve denetim programı

Staj boyunca yazılan tüm araçları (keşif, kanıtlı test, belge/link/görsel
denetim, doğrulama, yapay zekâ görsel denetimi, Bologna scraper, teslim
paketi) tek programdan, site profilleri ve ayarlarla çalıştırır.

Kullanım:
  python web_denetim.py                       # masaüstü arayüz
  python web_denetim.py --liste               # adımları listele
  python web_denetim.py --goster tam_test     # adımın komutlarını göster (çalıştırmaz)
  python web_denetim.py --calistir deneme     # adım(lar)ı komut satırından çalıştır
  python web_denetim.py --calistir tam-hat    # önerilen tam hattı çalıştır
  python web_denetim.py --durum               # çıktılardan özet
  python web_denetim.py --profiller           # site profillerini listele
  python web_denetim.py --yeni-profil "Örnek Üniversite" https://ornek.edu.tr/
  python web_denetim.py --profil ornek-universite --calistir kesif deneme
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
HATA_DOSYASI = Path(__file__).resolve().parent / "baslatma_hatasi.txt"


def baslatma_hatasi():
    """Program açılırken çökerse (pythonw ile pencere hiç görünmeden kapanır) hatayı dosyaya
    yazar ve bir pencerede gösterir. En sık neden: elle indirilen bir dosyanın eksik/bozuk olması."""
    import traceback
    metin = traceback.format_exc()
    try:
        HATA_DOSYASI.write_text(metin, encoding="utf-8")
    except OSError:
        pass
    sys.stderr.write(metin)
    if len(sys.argv) > 1:      # komut satırı kullanımında pencere açılmaz
        return
    try:
        import tkinter as tk
        from tkinter import messagebox
        kok = tk.Tk()
        kok.withdraw()
        son = "\n".join(metin.strip().splitlines()[-6:])
        messagebox.showerror(
            "Web Denetim Merkezi açılamadı",
            f"{son}\n\nTam hata: {HATA_DOSYASI}\n\nOlası neden: elle güncellenen bir dosya eksik ya da "
            "bozuk (ör. GitHub sayfası 'Farklı kaydet' ile HTML olarak kaydedilmiş). Dosyayı GitHub'da "
            "'Raw' görünümünden kaydedin ya da projeyi ZIP olarak yeniden indirin.")
        kok.destroy()
    except Exception:
        pass


try:
    from merkez import ayarlar as A  # noqa: E402
    from merkez.adimlar import ADIM, ADIMLAR, AI_HATTI, GRUPLAR, tam_hat  # noqa: E402
except Exception:
    if __name__ != "__main__":
        raise
    baslatma_hatasi()
    sys.exit(1)


def adim_listesi(isimler, ayar):
    sonuc = []
    for i in isimler:
        if i == "tam-hat":
            sonuc += tam_hat(ayar)
        elif i == "ai-hatti":
            sonuc += AI_HATTI
        elif i in ADIM:
            sonuc.append(i)
        else:
            sys.exit(f"Bilinmeyen adım: {i}  (liste için --liste)")
    return [ADIM[i] for i in sonuc]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Web Denetim Merkezi: web sitesi test ve denetim programı")
    p.add_argument("--profil", help="Kullanılacak site profili (varsayılan: son kullanılan)")
    p.add_argument("--liste", action="store_true", help="Adımları listele")
    p.add_argument("--goster", nargs="+", metavar="ADIM", help="Adımların komutlarını göster")
    p.add_argument("--calistir", nargs="+", metavar="ADIM",
                   help="Adımları sırayla çalıştır ('tam-hat', 'ai-hatti' de olur)")
    p.add_argument("--devam-et", action="store_true", help="Bir adım başarısız olsa da sürdür")
    p.add_argument("--durum", action="store_true", help="Çıktılardan özet göster")
    p.add_argument("--profiller", action="store_true", help="Site profillerini listele")
    p.add_argument("--yeni-profil", nargs=2, metavar=("AD", "URL"), help="Yeni site profili oluştur")
    a = p.parse_args()

    if a.yeni_profil:
        kimlik = A.yeni_profil(a.yeni_profil[0], a.yeni_profil[1])
        print(f"Profil oluşturuldu: {A.profil_dosyasi(kimlik)}")
        print(f"Sıradaki: python web_denetim.py --profil {kimlik} --calistir kesif deneme")
        return
    if a.profil and a.profil not in A.profiller():
        sys.exit(f"Profil yok: {a.profil}  (mevcut: {', '.join(A.profiller())})")
    ayar = A.yukle(profil=a.profil)

    if a.profiller:
        for pr in A.profiller():
            v = A.profil_oku(pr)
            isaret = "*" if pr == ayar["aktif_profil"] else " "
            print(f" {isaret} {pr:20s} {v['site_adi']:30s} {v['site_url']}")
        return
    if a.liste:
        for g, ad in GRUPLAR:
            print(f"\n{ad}")
            for adim in ADIMLAR:
                if adim.grup == g:
                    print(f"  {adim.id:20s} {adim.ad}" + (f"  [{adim.sure}]" if adim.sure else ""))
        print("\n  tam-hat              " + " → ".join(tam_hat(ayar)))
        print("  ai-hatti             " + " → ".join(AI_HATTI))
        return
    if a.goster:
        for adim in adim_listesi(a.goster, ayar):
            print(f"\n# {adim.ad}")
            for k in adim.komutlar(ayar):
                print("  " + k.goster())
        return
    if a.durum:
        from merkez.durum import ozet
        bolum = None
        for b, baslik, deger in ozet(ayar):
            if b != bolum:
                print(f"\n{b}")
                bolum = b
            print(f"  {baslik:32s} {deger}")
        return
    if a.calistir:
        from merkez.calistirici import Calistirici
        c = Calistirici(lambda m: (sys.stdout.write(m), sys.stdout.flush()))
        try:
            tamam = c.calistir(adim_listesi(a.calistir, ayar), ayar, devam_et=a.devam_et)
        except KeyboardInterrupt:
            c.durdur()
            tamam = False
        sys.exit(0 if tamam else 1)

    from merkez.arayuz import baslat
    baslat(ayar)


if __name__ == "__main__":
    try:
        main()
    except (SystemExit, KeyboardInterrupt, BrokenPipeError):
        raise
    except Exception:
        baslatma_hatasi()
        sys.exit(1)
