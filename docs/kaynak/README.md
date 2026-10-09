# Dokümantasyonun kaynağı

Bu klasörden iki belge üretilir; ikisi de Word (docx-js) ve PDF (LibreOffice) olarak:

| Belge | Üretim | Kaynak |
|---|---|---|
| `../KULLANIM_KILAVUZU.docx/.pdf` | `./derle.sh` | `kilavuz.js` |
| `../TEKNIK_DOKUMAN.docx/.pdf` | `./teknik_derle.sh` | `teknik.js` + `ortak.js` |

İçindekilerdeki sayfa numaraları iki geçişte bulunur (taslak PDF'ten başlıkların sayfaları okunur).

- `kilavuz.js`: kullanım kılavuzunun metni ve düzeni.
- `teknik.js`: teknik dokümanın metni (amaç, mimari, süreçler, sonuçların kaynağı, kod haritası);
  `ortak.js`: başlık, tablo, kutu, görsel gibi ortak yardımcılar.
- `veri_cikar.py`: kılavuzdaki adım ve ayar tablolarını programın kendi tanımlarından çıkarır;
  programa adım ya da ayar eklendiğinde tablolar kendiliğinden güncellenir.
- `img/`: ekran görüntüleri (programın gerçek çalışmasından, örnek bir sitede) ve teknik
  dokümanın diyagramları (`teknik_*.png`).
- `ekran/`: ekran görüntülerini yeniden çeken betikler. `ekran/cek.sh` küçük bir örnek site kurar
  (`ornek_site.py`), programı bu sitede gerçekten çalıştırır ve `img/` altındaki görüntüleri yeniler.
  Xvfb (`xvfb-run`) ve ImageMagick (`import`) gerekir:
  `GUI_PY=<tkinter'lı python> ARAC_PY=<playwright'lı python> EKSIK_PY=<paketsiz python> ./ekran/cek.sh`
- `diyagram/`: teknik dokümanın diyagramları (HTML). `python diyagram/ciz.py` (Playwright) ile
  `img/teknik_*.png` olarak yeniden çizilir.

Gerekenler: Node.js ve `docx` paketi (`npm install -g docx`), LibreOffice, poppler-utils,
tkinter'lı bir Python (kılavuzun tabloları için; `PYTHON=... ./derle.sh`).
