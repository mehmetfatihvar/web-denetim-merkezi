#!/bin/sh
# Web Denetim Merkezi'ni açar (Linux / macOS). İlk açılışta kurulumu kendisi yapar.
# Komut satırı seçenekleri de geçer: ./baslat.sh --liste
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "İlk çalıştırma: önce kurulum yapılıyor..."
    ./kurulum.sh || exit 1
fi
exec .venv/bin/python web_denetim.py "$@"
