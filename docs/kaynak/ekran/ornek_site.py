"""Kılavuz ekran görüntüleri için küçük örnek site üretir (43 sayfa, bilinçli kusurlarla).

Kusurlar: kırık sayfa linki, kırık ve sağlam PDF, editörün yerel dosya yolu, ölü alan adı,
taşan öğe, kırık görsel. Kullanım: python ornek_site.py HEDEF_KLASOR
"""
import sys
from pathlib import Path

k = Path(sys.argv[1])
bolumler = ["duyurular", "haberler", "akademik", "idari", "ogrenci", "iletisim"]
nav = "".join(f'<a href="/{b}/">{b.capitalize()}</a> ' for b in bolumler)


def sayfa(yol, baslik, govde):
    p = k / yol
    p.mkdir(parents=True, exist_ok=True)
    (p / "index.html").write_text(
        f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{baslik} | Örnek Üniversite</title></head><body><header><nav>{nav}</nav></header>'
        f'<main><h1>{baslik}</h1>{govde}</main><footer><a href="https://www.yok.gov.tr/">YÖK</a> '
        f'<a href="https://eski-portal.invalid/">Eski portal</a></footer></body></html>', encoding="utf-8")


sayfa("", "Ana sayfa", "<p>Örnek Üniversite'ye hoş geldiniz.</p>")
for b in bolumler:
    sayfa(b, b.capitalize(), "<ul>" + "".join(
        f'<li><a href="/{b}/{i}/">{b.capitalize()} {i}</a></li>' for i in range(1, 7)) + "</ul>")
    for i in range(1, 7):
        ek = ""
        if b == "duyurular" and i == 2:
            ek = '<a href="/duyurular/silinmis-duyuru/">Eski duyuru</a>'
        if b == "idari" and i == 1:
            ek = ('<a href="/belgeler/yonetmelik.pdf">Yönetmelik (PDF)</a> '
                  '<a href="/belgeler/kaldirilan.pdf">Eski form (PDF)</a> '
                  '<a href="file:///C:/Users/editor/Desktop/basvuru_formu.docx">Başvuru formu</a>')
        if b == "akademik" and i == 3:
            ek = '<div style="width:1600px;background:#eee">Geniş tablo taşması</div>'
        if b == "ogrenci" and i == 4:
            ek = '<img src="/yok.png" alt="">'
        sayfa(f"{b}/{i}", f"{b.capitalize()} {i}",
              f"<p>Bu sayfa {b} bölümünün {i}. sayfasıdır. Çağrı, şöyle, ığdır.</p>{ek}")
(k / "belgeler").mkdir(exist_ok=True)
(k / "belgeler" / "yonetmelik.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
print(sum(1 for _ in k.rglob("index.html")), "sayfa ->", k)
