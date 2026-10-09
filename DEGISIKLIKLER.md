# Değişiklikler

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
