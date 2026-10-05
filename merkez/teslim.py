"""TESLIM paketi: tüm çıktıları anlaşılır adlarla tek klasörde toplar.

tools/toparla.bat'ın her işletim sisteminde çalışan karşılığıdır; ek olarak
yapay zekâ denetimi çıktılarını da alır ve bir içindekiler sayfası üretir.
"""

import html
import shutil
from datetime import datetime
from pathlib import Path

from .ayarlar import Klasorler


def _dosyalar(k: Klasorler):
    """(kaynak, hedef alt yol, açıklama)"""
    return [
        (k.test / "report.html", "raporlar/test_raporu.html", "Kanıtlı test raporu"),
        (k.deneme / "report.html", "raporlar/deneme_test_raporu.html", "Deneme testi raporu"),
        (k.test / "report.xlsx", "veri/test_sonuclari.xlsx", "Test sonuçları (Excel)"),
        (k.test / "summary.txt", "veri/test_ozeti.txt", "Test özeti"),
        (k.test / "results.jsonl", "veri/ham_sonuclar.jsonl", "Ham test sonuçları"),
        (k.belge / "documents_audit.csv", "veri/belge_denetimi.csv", "Belge denetimi"),
        (k.link / "broken_links.csv", "veri/kirik_linkler.csv", "Kırık bağlantılar"),
        (k.gorsel / "gorsel_rapor.html", "raporlar/gorsel_rapor.html", "Görsel/UI kusur raporu"),
        (k.gorsel / "gorsel_denetim.csv", "veri/gorsel_denetim.csv", "Görsel kusur listesi"),
        (k.gorsel_ai / "gorsel_ai_rapor.html", "raporlar/yerel_ai_raporu.html",
         "Yerel model (Ollama) incelemesi"),
        (k.gorsel_ai / "gorsel_ai.csv", "veri/yerel_ai.csv", "Yerel model bulguları"),
        (k.rota_csv, "veri/rota_dogrulama.csv", "Kırık sayfa doğrulaması"),
        (k.tiklama_csv, "veri/tiklama_dogrulama.csv", "Buton tıklama doğrulaması"),
        (k.harita, "veri/site_haritasi.json", "Site haritası"),
        (k.kumeler, "veri/sablon_kumeleri.json", "Şablon kümeleri"),
        (k.denetim_cikti / "tarama.csv", "veri/piksel_tarama.csv", "Piksel taraması"),
        (k.denetim_cikti / "ozet.txt", "veri/piksel_tarama_ozeti.txt", "Piksel taraması özeti"),
        (k.ai_sonuc / "bulgular.csv", "veri/ai_bulgular.csv", "Yapay zekâ bulguları"),
        (k.ai_sonuc / "oylama.csv", "veri/ai_oylama.csv", "Modeller arası oylama"),
        (k.ai_sonuc / "ozet.txt", "veri/ai_ozeti.txt", "Yapay zekâ özeti (token, maliyet)"),
        (k.ai_sonuc / "isabet.txt", "veri/ai_isabet.txt", "Yapay zekâ isabet ölçümü"),
        (k.metin_csv, "veri/metin_kontrol.csv", "Metin kodlama denetimi"),
        (k.dogrulama_cikti / "ozet.txt", "veri/dogrulama_ozeti.txt", "Bulguların canlı doğrulaması"),
        (k.dogrulama_cikti / "sonuc.csv", "veri/dogrulama_sonuc.csv", "Doğrulama: bulgu başına karar"),
        (k.dogrulama_cikti / "kok_neden.csv", "veri/kok_neden.csv",
         "Kök neden: aynı öğeden kaynaklanan hatalar"),
        (k.etiket / "etiket_ozet.txt", "veri/etiket_ozeti.txt", "Elle etiketleme isabeti"),
        (k.etiket / "sonuc_etiketli.csv", "veri/sonuc_etiketli.csv", "Bulgular + insan etiketi"),
        (k.css_cikti / "css_ozet.txt", "veri/css_deneme_ozeti.txt", "CSS düzeltme denemesi"),
        (k.oto / "oneri.css", "raporlar/oneri.css", "Taşma düzeltme önerisi (CSS)"),
        (k.oto / "ozet.txt", "veri/oto_duzeltme_ozeti.txt", "Otomatik düzeltme özeti"),
    ]


def paketle(k: Klasorler, yaz) -> int:
    hedef = k.teslim
    (hedef / "raporlar").mkdir(parents=True, exist_ok=True)
    (hedef / "veri").mkdir(parents=True, exist_ok=True)
    alinan = []
    for kaynak, alt, aciklama in _dosyalar(k):
        if kaynak.exists():
            shutil.copy2(kaynak, hedef / alt)
            alinan.append((alt, aciklama))
            yaz(f"  + {alt}\n")
    # Son görsel denetim raporu kesit görselleriyle birlikte bir klasördür
    if (k.oto / "goruntu" / "karsilastir.html").exists():
        shutil.copytree(k.oto / "goruntu", hedef / "raporlar" / "tasma_duzeltme", dirs_exist_ok=True)
        alinan.append(("raporlar/tasma_duzeltme/karsilastir.html", "Taşma düzeltme: önce/sonra"))
        yaz("  + raporlar/tasma_duzeltme/ (önce/sonra görüntüler)\n")
    if (k.ai_rapor / "rapor.html").exists():
        shutil.copytree(k.ai_rapor, hedef / "raporlar" / "gorsel_denetim", dirs_exist_ok=True)
        alinan.append(("raporlar/gorsel_denetim/rapor.html", "Yapay zekâ görsel denetim son raporu"))
        yaz("  + raporlar/gorsel_denetim/ (kesitlerle)\n")
    if not alinan:
        yaz("Pakete alınacak çıktı bulunamadı. Önce test/denetim adımlarını çalıştırın.\n")
        return 1
    _index_yaz(hedef, alinan)
    ekran = k.test / "screenshots"
    yaz(f"\nTESLIM hazır: {hedef}  ({len(alinan)} dosya)\n")
    if ekran.exists():
        yaz(f"Kanıt görüntüleri büyük olduğu için pakete kopyalanmadı; ayrıca ZIP'leyin:\n  {ekran}\n")
    return 0


def _index_yaz(hedef: Path, alinan):
    E = html.escape
    satirlar = "".join(
        f'<tr><td><a href="{E(alt)}">{E(alt)}</a></td><td>{E(aciklama)}</td></tr>'
        for alt, aciklama in alinan)
    (hedef / "index.html").write_text(f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Teslim Paketi</title>
<style>body{{font:15px system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1f2328}}
main{{max-width:960px;margin:auto;padding:24px 16px}} table{{width:100%;border-collapse:collapse;background:#fff}}
td,th{{border:1px solid #dde1e7;padding:8px;text-align:left}} th{{background:#eef1f5}} a{{color:#0b57d0}}</style>
</head><body><main><h1>Teslim Paketi</h1><p>Oluşturma: {datetime.now():%Y-%m-%d %H:%M}</p>
<table><tr><th>Dosya</th><th>İçerik</th></tr>{satirlar}</table></main></body></html>""",
                                      encoding="utf-8")


def index_yolu(k: Klasorler):
    p = k.teslim / "index.html"
    return p if p.exists() else None
