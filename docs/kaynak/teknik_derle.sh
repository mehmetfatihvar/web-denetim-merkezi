#!/bin/sh
# Teknik dokümanı üretir: docs/TEKNIK_DOKUMAN.docx ve .pdf
# Gerekenler: Node.js + docx (npm), LibreOffice (soffice), poppler-utils (pdfinfo, pdftotext).
# Diyagramlar: python diyagram/ciz.py (Playwright) -> img/teknik_*.png
# İki geçiş: taslak PDF'ten başlıkların sayfaları bulunur, içindekiler bu numaralarla yeniden yazılır.
set -e
cd "$(dirname "$0")"

node teknik.js taslak.docx >/dev/null
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
node teknik.js ../TEKNIK_DOKUMAN.docx sayfalar.json
soffice --headless --convert-to pdf --outdir .. ../TEKNIK_DOKUMAN.docx >/dev/null 2>&1
rm -f taslak.docx taslak.pdf basliklar.json sayfalar.json
pdfinfo ../TEKNIK_DOKUMAN.pdf | grep Pages
