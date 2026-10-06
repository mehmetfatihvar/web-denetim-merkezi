# Kullanım kılavuzunun kaynağı

`../KULLANIM_KILAVUZU.docx` ve `../KULLANIM_KILAVUZU.pdf` buradan üretilir:

```bash
./derle.sh
```

- `kilavuz.js`: kılavuzun metni ve düzeni (docx-js).
- `veri_cikar.py`: adım ve ayar tablolarını programın kendi tanımlarından çıkarır; programa adım ya da
  ayar eklendiğinde tablolar kendiliğinden güncellenir.
- `img/`: ekran görüntüleri (programın gerçek çalışmasından, örnek bir sitede).
- `ekran/`: ekran görüntülerini yeniden çeken betikler. `ekran/cek.sh` küçük bir örnek site kurar
  (`ornek_site.py`), programı bu sitede gerçekten çalıştırır ve `img/` altındaki görüntüleri yeniler.
  Xvfb (`xvfb-run`) ve ImageMagick (`import`) gerekir:
  `GUI_PY=<tkinter'lı python> ARAC_PY=<playwright'lı python> EKSIK_PY=<paketsiz python> ./ekran/cek.sh`

Gerekenler: Node.js ve `docx` paketi (`npm install -g docx`), LibreOffice, poppler-utils, Python + tkinter.
