#!/bin/sh
# Web Denetim Merkezi - kurulum (Linux / macOS)
# Repo içinde .venv sanal ortamını kurar, paketleri ve Chromium'u indirir.
set -e
cd "$(dirname "$0")"
PY=""
for aday in python3 python; do
    if command -v "$aday" >/dev/null 2>&1; then PY="$aday"; break; fi
done
if [ -z "$PY" ]; then
    echo "[HATA] Python bulunamadı. Python 3.9+ kurun (https://www.python.org/downloads/)."; exit 1
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "[HATA] Python 3.9 veya üstü gerekli: $("$PY" --version)"; exit 1; }
"$PY" -c 'import tkinter' 2>/dev/null || {
    echo "[!] tkinter yok; arayüz açılmaz (komut satırı çalışır)."
    echo "    Debian/Ubuntu: sudo apt install python3-tk   ·   macOS (Homebrew): brew install python-tk"; }
if [ ! -x .venv/bin/python ]; then
    echo "[1/3] Sanal ortam oluşturuluyor: .venv"
    "$PY" -m venv .venv || { echo "[HATA] venv kurulamadı (Debian/Ubuntu: sudo apt install python3-venv)"; exit 1; }
else
    echo "[1/3] Sanal ortam zaten var: .venv"
fi
echo "[2/3] Python paketleri kuruluyor..."
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
echo "[3/3] Chromium tarayıcısı indiriliyor..."
.venv/bin/python -m playwright install chromium
echo
echo "Kurulum tamam. Programı ./baslat.sh ile açın."
