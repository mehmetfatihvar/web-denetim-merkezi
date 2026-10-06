#!/bin/sh
# Kılavuzun ekran görüntülerini yeniden çeker. Gerekenler: Xvfb (xvfb-run), ImageMagick (import),
# tkinter'lı bir Python (GUI_PY) ve playwright'lı bir Python (ARAC_PY). Program klasörüne geçici bir
# 'ornek-universite' profili ve çıktısı yazılır; iş bitince silinir.
set -e
cd "$(dirname "$0")"
GUI_PY=${GUI_PY:-python3}; ARAC_PY=${ARAC_PY:-python3}; EKSIK_PY=${EKSIK_PY:-$GUI_PY}
KOK=$(cd ../../.. && pwd); IMG=$(cd .. && pwd)/img; GECICI=$(mktemp -d)
"$ARAC_PY" ornek_site.py "$GECICI/site"
(cd "$GECICI/site" && exec "$ARAC_PY" -m http.server 8765 >/dev/null 2>&1) & SUNUCU=$!
trap 'kill $SUNUCU 2>/dev/null; rm -rf "$GECICI" "$KOK/profiller/ornek-universite.json" "$KOK/ciktilar/ornek-universite"' EXIT
cp "$KOK/ayarlar.json" "$GECICI/ayarlar.yedek" 2>/dev/null || true
sleep 1
xvfb-run -a -s "-screen 0 1320x900x24" "$GUI_PY" arayuz_goruntuleri.py "$IMG" "$ARAC_PY"
xvfb-run -a -s "-screen 0 1320x900x24" "$GUI_PY" arayuz_goruntuleri.py "$IMG" "$EKSIK_PY" uyari
"$ARAC_PY" rapor_goruntuleri.py "$IMG" "$KOK/ciktilar/ornek-universite"
if [ -f "$GECICI/ayarlar.yedek" ]; then cp "$GECICI/ayarlar.yedek" "$KOK/ayarlar.json"; else rm -f "$KOK/ayarlar.json"; fi
echo "Görüntüler: $IMG"
