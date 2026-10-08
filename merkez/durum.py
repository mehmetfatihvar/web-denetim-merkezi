"""Çıktı dosyalarından durum ve özet sayılar (arayüzdeki 'Durum' sekmesi)."""

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .adimlar import ADIM as ADIM_SOZLUK, ADIMLAR, Adim, harita_url_sayisi, onbellekli
from .ayarlar import Klasorler


_SORUNLU_BELGE = ("SIZDIRILMIS", "KIRIK", "ULASILAMADI")   # tester'ın documents_audit.csv işaretleri


def cikti_durumu(adim: Adim, ayar: dict) -> Tuple[bool, Optional[datetime]]:
    """Adımın ana çıktısı var mı, en son ne zaman üretildi."""
    try:
        yollar = adim.ciktilar(ayar)
    except Exception:
        return False, None
    zamanlar = [datetime.fromtimestamp(p.stat().st_mtime) for p in yollar if p.exists()]
    return bool(zamanlar), (max(zamanlar) if zamanlar else None)


def csv_satirlari(yol: Path) -> List[dict]:
    """';' veya ',' ayraçlı CSV'yi okur (araçlar ikisini de kullanıyor)."""
    return onbellekli(yol, _csv_oku)


def _csv_oku(yol: Path) -> List[dict]:
    try:
        with open(yol, encoding="utf-8-sig", newline="") as f:
            ilk = f.readline()
            f.seek(0)
            ayrac = ";" if ilk.count(";") > ilk.count(",") else ","
            return list(csv.DictReader(f, delimiter=ayrac))
    except OSError:
        return []


def _jsonl(yol: Path) -> List[dict]:
    return onbellekli(yol, _jsonl_oku)


def _jsonl_oku(yol: Path) -> List[dict]:
    kayitlar = {}
    try:
        with open(yol, encoding="utf-8") as f:
            for satir in f:
                try:
                    r = json.loads(satir)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                # aynı URL tekrar test edildiyse sonuncusu; özet için gereken alanlar yeter
                # (kayıtlar büyük olabilir, önbellekte bellek şişmesin)
                kayitlar[r.get("url")] = {
                    "url": r.get("url"), "overall": r.get("overall"), "http_status": r.get("http_status"),
                    "js_errors": bool(r.get("js_errors")),
                    "accessibility": {"missing_h1": bool((r.get("accessibility") or {}).get("missing_h1"))}}
    except OSError:
        return []
    return list(kayitlar.values())


def ozet(ayar: dict) -> List[Tuple[str, str, str]]:
    """(bölüm, başlık, değer) satırları. Yalnızca var olan çıktılar raporlanır."""
    k = Klasorler(ayar)
    s = []
    n = harita_url_sayisi(k.harita)
    s.append(("Site", "Profil", f'{ayar["site_adi"]}  ({ayar["site_url"]})'))
    s.append(("Site", "Site haritası", f"{n:,} sayfa".replace(",", ".") if n else "yok — önce keşif"))
    if k.kumeler.exists():
        try:
            veri = json.loads(k.kumeler.read_text(encoding="utf-8"))
            s.append(("Site", "Şablon sayısı", str(veri.get("template_count", "?"))))
        except ValueError:
            pass

    test, bolum = _jsonl(k.test / "results.jsonl"), "Web testi"
    if not test:
        test, bolum = _jsonl(k.deneme / "results.jsonl"), "Deneme testi"
    if test:
        genel = Counter(r.get("overall") for r in test)
        durum = Counter(r.get("http_status") for r in test)
        s.append((bolum, "Test edilen sayfa", str(len(test))))
        s.append((bolum, "Başarılı (200)", str(durum.get(200, 0))))
        s.append((bolum, "Geçti / uyarı / kaldı / hata",
                  f'{genel.get("pass", 0)} / {genel.get("warn", 0)} / {genel.get("fail", 0)} / '
                  f'{genel.get("error", 0)}'))
        kirik = sum(v for d, v in durum.items() if isinstance(d, int) and d >= 400)
        s.append((bolum, "4xx/5xx dönen sayfa", str(kirik)))
        s.append((bolum, "JS hatalı sayfa", str(sum(1 for r in test if r.get("js_errors")))))
        s.append((bolum, "H1 eksik", str(sum(
            1 for r in test if (r.get("accessibility") or {}).get("missing_h1")))))

    link = k.link / "broken_links.csv"
    if link.exists():
        s.append(("Denetimler", "Kırık bağlantı", str(len({r.get("url") for r in csv_satirlari(link)}))))
    belge = k.belge / "documents_audit.csv"
    if belge.exists():
        tekil = {r.get("url"): r for r in csv_satirlari(belge)}
        sorunlu = sum(1 for r in tekil.values() if (r.get("flag") or "").startswith(_SORUNLU_BELGE))
        s.append(("Denetimler", "Belge (toplam / sorunlu)", f"{len(tekil)} / {sorunlu}"))
    if (k.gorsel / "gorsel_denetim.csv").exists():
        s.append(("Denetimler", "Görsel kusur", str(len(csv_satirlari(k.gorsel / "gorsel_denetim.csv")))))

    for baslik, yol in (("Rota doğrulama", k.rota_csv), ("Tıklama doğrulama", k.tiklama_csv)):
        if yol.exists():
            dagilim = Counter(r.get("verdict", "?") for r in csv_satirlari(yol))
            s.append(("Doğrulama", baslik,
                      ", ".join(f"{v}: {n}" for v, n in dagilim.most_common())))

    tarama = k.denetim_cikti / "tarama.csv"
    if tarama.exists():
        s.append(("Yapay zekâ", "Piksel taranan görüntü", str(len(csv_satirlari(tarama)))))
    if (k.denetim_cikti / "ornekler.csv").exists():
        s.append(("Yapay zekâ", "Temsilci görüntü",
                  str(len(csv_satirlari(k.denetim_cikti / "ornekler.csv")))))
    oylama = k.ai_sonuc / "oylama.csv"
    if oylama.exists():
        karar = Counter(r.get("karar") for r in csv_satirlari(oylama))
        s.append(("Yapay zekâ", "Bulgu (kesin / incele)",
                  f'{karar.get("KESIN", 0)} / {karar.get("INCELE", 0)}'))
    if k.metin_csv.exists():
        s.append(("Yapay zekâ", "Metin kodlama bulgusu", str(len(csv_satirlari(k.metin_csv)))))
    sonuc = k.dogrulama_cikti / "sonuc.csv"
    if sonuc.exists():
        karar = Counter(r.get("karar") for r in csv_satirlari(sonuc))
        s.append(("Doğrula ve düzelt", "Canlı doğrulama",
                  ", ".join(f"{a}: {n}" for a, n in karar.most_common())))
    kok = k.dogrulama_cikti / "kok_neden.csv"
    if kok.exists():
        s.append(("Doğrula ve düzelt", "Kök neden (tek düzeltme, çok sayfa)", str(len(csv_satirlari(kok)))))
    turlar = k.oto / "turlar.csv"
    if turlar.exists():
        son = (csv_satirlari(turlar) or [{}])[-1]
        s.append(("Doğrula ve düzelt", "Otomatik düzeltme (son tur)",
                  ", ".join(f"{a}: {v}" for a, v in son.items() if v not in (None, ""))))
    return s


def adim_durumlari(ayar: dict):
    return {a.id: cikti_durumu(a, ayar) for a in ADIMLAR}


# ------------------------------------------------------------- ana sayfa

def kutucuklar(ayar: dict) -> List[Tuple[str, str, str, str]]:
    """Ana sayfadaki özet kutucukları: (başlık, değer, alt metin, vurgu: ''|'vurgu'|'hata')."""
    k = Klasorler(ayar)
    n = harita_url_sayisi(k.harita)
    sayi = lambda v: f"{v:,}".replace(",", ".")  # noqa: E731
    kutu = [("Site haritası", sayi(n) if n else "—", "sayfa" if n else "önce site keşfi", "vurgu")]
    test = _jsonl(k.test / "results.jsonl") or _jsonl(k.deneme / "results.jsonl")
    if test:
        kirik = sum(1 for r in test if isinstance(r.get("http_status"), int) and r["http_status"] >= 400)
        kutu.append(("Test edilen", sayi(len(test)), f"sayfa · %{len(test) / n * 100:.0f} kapsam"
                     if n else "sayfa", ""))
        kutu.append(("Kırık sayfa", sayi(kirik), "4xx / 5xx dönen", "hata" if kirik else ""))
    else:
        kutu.append(("Test edilen", "—", "henüz test yok", ""))
    link = k.link / "broken_links.csv"
    if link.exists():
        kutu.append(("Kırık bağlantı", sayi(len({r.get("url") for r in csv_satirlari(link)})), "iç + dış", "hata"))
    belge = k.belge / "documents_audit.csv"
    if belge.exists():
        tekil = {r.get("url"): r for r in csv_satirlari(belge)}
        sorunlu = sum(1 for r in tekil.values() if (r.get("flag") or "").startswith(_SORUNLU_BELGE))
        kutu.append(("Sorunlu belge", sayi(sorunlu), f"{sayi(len(tekil))} belgeden", "hata" if sorunlu else ""))
    gorsel = k.gorsel / "gorsel_denetim.csv"
    if gorsel.exists():
        kutu.append(("Görsel kusur", sayi(len(csv_satirlari(gorsel))), "şablon temsilcilerinde", ""))
    oylama = k.ai_sonuc / "oylama.csv"
    if oylama.exists():
        kesin = sum(1 for r in csv_satirlari(oylama) if r.get("karar") == "KESIN")
        kutu.append(("Yapay zekâ bulgusu", sayi(kesin), "kesin (2+ model)", ""))
    return kutu


def _var(adim_id: str, ayar: dict) -> bool:
    return cikti_durumu(ADIM_SOZLUK[adim_id], ayar)[0]


def kapsam_oku(k) -> dict:
    """analiz.py'nin yazdığı kapsam.json (ilk model / hakem kaç dilime baktı)."""
    return onbellekli(k.ai_sonuc / "kapsam.json", _json_oku)


def _json_oku(yol) -> dict:
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _kapsam_durumu(k, anahtar):
    """(tamam mı, ayrıntı). Hakemde kayıt yoksa tamam=None (rapor varlığına bakılır)."""
    kayit = kapsam_oku(k).get(anahtar)
    if not kayit or not kayit.get("modeller"):
        return (False if anahtar == "ilk_model" else None), ""
    tamam, parca = True, []
    for m in kayit["modeller"]:
        eksik = m["denenmedi"] + m.get("kota", 0)
        tamam = tamam and (not eksik if anahtar == "ilk_model" else not (eksik or m["yapilamadi"]))
        metin = f"{m['tamam']}/{m['beklenen']} dilim"
        if m["yapilamadi"]:
            metin += f", {m['yapilamadi']} yapılamadı"
        if m["denenmedi"]:
            metin += f", {m['denenmedi']} denenmedi"
        parca.append(metin)
    return tamam, "; ".join(parca)


def yol_haritasi(ayar: dict):
    """Önerilen iş sırası: (başlık, açıklama, tamam mı, ayrıntı, çalıştırılacak adımlar)."""
    k = Klasorler(ayar)
    n = harita_url_sayisi(k.harita)
    asamalar = [
        ("Site haritası", "Sitenin tıklanabilir sayfaları keşfedilir.", ["kesif"],
         lambda: (n > 0, f"{n:,} sayfa".replace(",", ".") if n else "")),
        ("Deneme testi", "İlk birkaç sayfa test edilip sonuçlara bakılır.", ["deneme"],
         lambda: (_var("deneme", ayar) or _var("tam_test", ayar), "")),
        ("Tüm site testi", "Bütün sayfalar kanıtlı olarak test edilir.", ["tam_test"],
         lambda: (_var("tam_test", ayar), "")),
        ("Denetimler", "Belge, kırık link ve görsel kusur denetimleri.",
         ["belge", "link", "kumeleme", "gorsel"], None),
        ("Doğrulama", "Kırık sayfalar doğrudan erişim ve tıklamayla teyit edilir.",
         ["rota", "tiklama"], None),
        ("Yapay zekâ: hazırlık", "Görüntüler kodla taranır, şablon temsilcileri seçilip yeniden çekilir.",
         ["ai_tarama", "ai_temsilci", "ai_yeniden"], None),
        ("Yapay zekâ: ilk model", "Temsilci görüntülerin her dilimi ilk modele sorulur.",
         ["ai_analiz"], lambda: _kapsam_durumu(k, "ilk_model")),
        ("Yapay zekâ: hakem ve rapor", "Şüpheli ve ilk modelin bakamadığı dilimler hakeme gider, "
         "son rapor üretilir.", ["ai_hakem", "ai_isabet", "ai_metin", "ai_rapor"],
         lambda: (_var("ai_rapor", ayar) and _kapsam_durumu(k, "hakem")[0] is not False,
                  _kapsam_durumu(k, "hakem")[1])),
        ("Canlı doğrulama", "Bulgular canlı sitede yeniden ölçülür: gerçek mi, yanlış alarm mı? (7)",
         ["gd_dogrulama"], None),
        ("Elle etiketleme: sayfa", "Sayfayı açıp bulguları 1/2/3 ile işaretleyin, 'CSV indir'e basın. (8a)", ["gd_etiket"], None),
        ("Elle etiketleme: sonuç", "İndirilen etiketlerden isabet hesaplanır; etiketlemeden sonra "
         "çalıştırın. (8b)", ["gd_etiket_ozet"], None),
        ("Taşma düzeltme", "Taşma için CSS önerisi üretilir ve canlı sayfada denenir. (10, 9)",
         ["gd_oto", "gd_css"], None),
        ("Teslim paketi", "Bütün rapor ve veriler tek klasörde toplanır.", ["teslim"],
         lambda: (_var("teslim", ayar), "")),
    ]
    sonuc = []
    for baslik, aciklama, ids, kontrol in asamalar:
        eksik = [i for i in ids if not _var(i, ayar) and ADIM_SOZLUK[i].ciktilar(ayar)]
        if kontrol:
            tamam, ayrinti = kontrol()
        else:
            tamam = not eksik
            ayrinti = f"{len(ids) - len(eksik)}/{len(ids)} adım" if eksik and len(eksik) < len(ids) else ""
        calistir = (eksik or ids) if not tamam else ids
        sonuc.append((baslik, aciklama, tamam, ayrinti, calistir))
    return sonuc
