# Değişiklikler

## 1.4.2 (Ekim 2026)

- Ana sayfa kutularının alt yazısı dar pencerede kesilmez (satır kaydırır); yapay zekâ kutusunun
  yazısı kısaldı ("kesin · sayfa-hata").

## 1.4.1 (Ekim 2026)

- Ana sayfadaki "Yapay zekâ bulgusu" kutusu son raporla aynı sayıyı gösterir (kesin sayfa-hata çifti;
  rapor `ozet.json` yazar). Önceden oylama.csv'deki bütün kesin dilimleri sayıyordu (ör. 172 / raporda 94).
- Hakem yeniden çalışıp son rapor eskidiyse yol haritası "hakem ve rapor" aşamasını tamam saymaz;
  Başlat yalnız raporu yeniden üretir. Kutu o arada ham dilim sayısını "rapor eski" notuyla gösterir.

## 1.4 (Ekim 2026)

- **Kalanları da sırayla çalıştır** etiketlemede durmaz: 8a'yı (etiketleme sayfası) oluşturur, sizi
  bekleyen 8b'yi atlayıp taşma düzeltme ve teslimle devam eder. Onay penceresi etiketlemenin size
  kaldığını ⚠ ile yazar; bitince etiketleme sayfasını açmayı önerir.
- **Bu sayfadakileri sırayla çalıştır** hepsi işaretli gelir; işaretsiz kalan birkaç adımın nedeni
  yanında yazar (ör. "Tüm siteyi tara kapsar", "Go kurulu olmalı", "etiketlemeden sonra").

## 1.3.1 (Ekim 2026)

- Sade görünümde onay kutuları işaretliyken çarpı (☒) yerine vurgu renginde ✓ gösterir; ekran
  ölçeklemesine göre boyutlanır.
- Adım sayfalarında ayrıntı kartının genişliği, seçilen adıma göre değişmez (liste ve kart hep 3:2).

## 1.3 (Ekim 2026)

- Her adım sayfasında **Bu sayfadakileri sırayla çalıştır…**: sayfadaki adımlar işaretli bir listede
  gelir (önerilenler işaretli: ör. Web testi'nde tüm site testi + hatalı sayfaları yeniden test,
  Bologna'da PostgreSQL + tüm site + istatistik), seçilenler sırayla çalışır. 8a ile 8b birlikte
  çalışmaz; 9, 10'dan sonra çalışır.

## 1.2 (Ekim 2026)

**Arayüz: daha az düğme, çalışıp çalışmadığı belli**
- Çalıştırmanın iki yolu kaldı: ana sayfadaki **Başlat** (sıradaki aşama) ve adım sayfasındaki
  **Çalıştır** (tek adım). "Seçilenleri çalıştır", seçim kutuları, Ctrl+Enter, çift tıklayınca
  çalıştırma ve üst çubuktaki Tam hat / Yapay zekâ hattı düğmeleri kaldırıldı.
- Ana sayfada **Sıradaki adım** kartı; **Kalanları da sırayla çalıştır** kalan aşamaları arka
  arkaya çalıştırır, elle etiketlemede durur. Yol haritası satırına tıklamak o sayfayı açar.
- Adım kartında üç düğme: Çalıştır, Sonucu aç, Diğer ▾ (adım raporu, klasör, komut).
- Her zaman görünen **durum şeridi**: dönen gösterge, "Adım 2/8", aracın son hareket zamanı;
  2 dk çıktı yoksa sarı uyarı, 10 dk yoksa "takılmış olabilir" ve ne yapılacağı. Menüde çalışan
  sayfanın yanında da gösterge döner. Durdur yalnız çalışırken görünür.
- Kayıt / hatalar / son çalışma **Ayrıntılar** panelinde; adım başarısız olursa kendiliğinden açılır.
- "Hata olursa sonraki adımlarla sürdür" Ayarlar > Genel'e taşındı.

**Bologna: her OİBS sitesi**
- Varsayılan Mersin Üniversitesi; başka bir üniversite `--base-url obs.ornek.edu.tr` (arayüzde
  profilin OİBS Bologna adresi ya da Yeni site penceresi) ile taranır. Alan adı yeter.
- Her site aynı veritabanında kendi şemasına yazılır (MEÜ: `public`, diğerleri adresten türetilir,
  `--schema` ile elle); `site_info` başka bir sitenin aynı şemaya yazılmasını engeller.
- `-p` ile başka bir sitenin program adresi verilirse o siteye geçilir; `stats` site ve şemayı yazar.

## 1.1 (Ekim 2026)

**Yapay zekâ görsel denetimi**
- İlk model ve hakem ayrı aşamalar: ilk model yapılamayan istekleri aynı çalıştırmada 2 tur daha
  dener, kapsamı `kapsam.json`'a yazar; hiç denenmemiş ya da kota yüzünden kalan dilim varsa
  hakeme geçilmez. Hakem, ilk modelin bakamadığı her dilime (yalnız Gemma 500 değil) bakar.
- Gemini isteklerine 5 dk zaman aşımı; 504 / DEADLINE_EXCEEDED yeniden denenir.
- İlerleme satırında başarılı / yapılamayan sayısı: `[340/3792] ✓ 270 başarılı ✗ 70 yapılamadı`.
- Tamamlanmış görüntüler yeniden başlatmada dilimlenmez.

**Doğrula ve düzelt**
- 8b (etiketleri işle) etiketleme yapılmadan çalışmaz; 8a'dan sonra indirilmiş etiket dosyasını
  (`etiketler (1).csv` dahil) kendisi bulur. "Seçilenleri çalıştır"da 8a ile birlikte seçilirse
  çıkarılır.

**Arayüz**
- Ana sayfa yol haritası: yapay zekâ (hazırlık / ilk model / hakem ve rapor) ve doğrula-düzelt
  (canlı doğrulama / etiketleme sayfası / etiketleme sonucu / taşma düzeltme) ayrı satırlar.
- Raporlar: "Etiketleme sayfası (8a)" düğmesi.
- Varsayılan "sade" görünüm (Windows'ta çok daha hızlı); sayfa ve tema geçişlerinde titreme yok.
- Her adımın HTML raporu (`adim_raporlari/`), kırık link raporunda teyit sütunu, kırık belge raporu.
- Açılışta çökme artık görünür: hata penceresi + `baslatma_hatasi.txt`.
- "Program bulunamadı" hatasında programın adı ve Docker/Go için ne yapılacağı yazılır.

**Dokümantasyon**
- Teknik doküman (`docs/TEKNIK_DOKUMAN.pdf`): amaç, mimari, süreçler, sonuçların kaynağı, kod haritası.
- Kullanım kılavuzu: ZIP ile güncelleme, Docker/WSL sorun giderme, yeni aşamalar.

## 1.0 (5 Ekim 2026)

İlk sürüm: staj araçlarının tek masaüstü programında birleştirilmesi, site profilleri, tam hat,
yapay zekâ hattı, doğrula ve düzelt, Bologna, teslim paketi, kullanım kılavuzu.
