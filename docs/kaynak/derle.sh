#!/bin/sh
# Kullanım kılavuzunu üretir: docs/KULLANIM_KILAVUZU.docx ve .pdf
# Gerekenler: Node.js + docx (npm), LibreOffice (soffice), poppler-utils (pdfinfo, pdftotext), Python + tkinter.
# İki geçiş: taslak PDF'ten başlıkların sayfaları bulunur, içindekiler bu numaralarla yeniden yazılır.
set -e
cd "$(dirname "$0")"
"${PYTHON:-python3}" veri_cikar.py   # tkinter içeren bir Python (PYTHON=... ile seçilebilir)
node kilavuz.js taslak.docx >/dev/null
soffice --headless --convert-to pdf taslak.docx >/dev/null 2>&1
python3 - <<'PY'
import json, subprocess
b = json.load(open("basliklar.json", encoding="utf-8"))
n = int(subprocess.run(["pdfinfo", "taslak.pdf"], capture_output=True, text=True).stdout.split("Pages:")[1].split()[0])
sf = [[s.strip() for s in subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", "taslak.pdf", "-"],
       capture_output=True, text=True).stdout.splitlines()] for i in range(1, n + 1)]
out, bas = {}, 0
for h in b:
    for i in range(bas, n):
        if h in sf[i]:
            out[h] = i + 1; bas = i; break
json.dump(out, open("sayfalar.json", "w", encoding="utf-8"), ensure_ascii=False)
print("içindekiler:", len(out), "/", len(b), "başlık")
PY
node kilavuz.js ../KULLANIM_KILAVUZU.docx sayfalar.json
soffice --headless --convert-to pdf --outdir .. ../KULLANIM_KILAVUZU.docx >/dev/null 2>&1
rm -f taslak.docx taslak.pdf basliklar.json sayfalar.json veri.json
pdfinfo ../KULLANIM_KILAVUZU.pdf | grep Pages
