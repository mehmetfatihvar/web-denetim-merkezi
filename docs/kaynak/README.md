# Kullanım kılavuzunun kaynağı

`../KULLANIM_KILAVUZU.docx` ve `../KULLANIM_KILAVUZU.pdf` buradan üretilir:

```bash
./derle.sh
```

- `kilavuz.js`: kılavuzun metni ve düzeni (docx-js).
- `veri_cikar.py`: adım ve ayar tablolarını programın kendi tanımlarından çıkarır; programa adım ya da
  ayar eklendiğinde tablolar kendiliğinden güncellenir.
- `img/`: ekran görüntüleri (programın gerçek çalışmasından, örnek bir sitede).

Gerekenler: Node.js ve `docx` paketi (`npm install -g docx`), LibreOffice, poppler-utils, Python + tkinter.
