# Web Denetim Merkezi

Bir web sitesini baştan sona test eden ve denetleyen masaüstü programı. Bütün işler tek
pencereden yapılır:
- site keşfi, kanıtlı tarayıcı testi
- belge, kırık link ve görsel/UI kusur denetimi, kırık sayfa doğrulaması
- yapay zekâ destekli görsel denetim, bulguların canlı sitede doğrulanması ve taşma için
  otomatik CSS düzeltme önerisi
- OİBS Bologna Bilgi Paketi taraması
- teslim paketi

**Site profilleriyle her siteye uygulanır.** Yapay zekâ sağlayıcıları ve modeller ayarlardan
seçilir. Program, Mersin Üniversitesi ÖİDB web sitesi için yapılan staj çalışmasından
([mehmetfatihvar/staj](https://github.com/mehmetfatihvar/staj)) doğdu; ÖİDB hazır profil olarak
gelir.

---

## 1. Kurulum (başka bir bilgisayarda)

Gereken tek şey **Python 3.9 veya üstü**. Windows'ta [python.org](https://www.python.org/downloads/)
kurulumunda "Add python.exe to PATH" kutusunu işaretleyin.

**Windows**

1. Repoyu indirin: `git clone https://github.com/mehmetfatihvar/web-denetim-merkezi.git`
   (veya GitHub'dan ZIP olarak indirip açın).
2. `BASLAT.bat` dosyasına çift tıklayın.

İlk açılışta `KURULUM.bat` kendiliğinden çalışır. Repo klasöründe ayrı bir sanal ortam
(`.venv`) kurar, paketleri ve Chromium tarayıcısını indirir; bilgisayardaki diğer Python
kurulumlarına dokunmaz. Sonraki açılışlar doğrudan programı açar.

**Linux / macOS**

```bash
git clone https://github.com/mehmetfatihvar/web-denetim-merkezi.git
cd web-denetim-merkezi
./baslat.sh          # ilk açılışta ./kurulum.sh çalışır
```

Linux'ta arayüz için `python3-tk` ve `python3-venv` gerekebilir:
`sudo apt install python3-tk python3-venv`.

**Bologna** için ayrıca Docker Desktop **veya** Go ile PostgreSQL gerekir (bkz.
[bologna-scraper/README.md](bologna-scraper/README.md)). Web testi için gerekmez.

Program açılınca bu bilgisayardaki eksikleri (paket, Chromium) denetler ve varsa ana sayfada
uyarı ile **Bağımlılıkları kur** düğmesini gösterir. Ayrıntılı döküm için **Hazırlık > Ortam
kontrolü**.

**Güncelleme:** `git pull`, ardından `KURULUM.bat` (veya `./kurulum.sh`) bir kez daha.

---

## 2. Arayüz

Pencerenin solunda menü, sağında seçilen sayfa, altında ilerleme paneli ve çalışma kaydı var.

- **Sol menü:**
  - Site profili seçimi ve **Yeni site ekle**.
  - Sayfalar: Ana sayfa, Hazırlık, Web testi, Denetimler, Doğrulama, Yapay zekâ denetimi,
    Doğrula ve düzelt, Bologna, Teslim, Raporlar ve özet, Ayarlar.
  - En altta açık/karanlık tema düğmesi.
- **Ana sayfa:**
  - Özet kutucukları: site haritası, test edilen sayfa ve kapsam, kırık sayfa, kırık bağlantı,
    görsel kusur, yapay zekâ bulgusu.
  - **Yol haritası:** önerilen sıra (keşif → deneme → tüm site → denetimler → doğrulama →
    yapay zekâ → teslim). Tamamlanan aşamalar ✔ ile işaretlidir. **Sıradaki** aşama tek
    tıkla başlatılır; yalnız eksik kalan adımlar çalışır.
  - Var olan raporlara kısayollar.
- **Adım sayfaları:**
  - Solda adım listesi: tahmini süre ve durum (son çıktı zamanı, çalışırken canlı yüzde,
    bitince başarılı/başarısız).
  - Sağda seçili adımın kartı: açıklama, çıktı dosyaları, **Çalıştır**, **Çıktıyı aç**,
    **Klasörü aç** ve çalışacak komutu kayda yazma.
  - Satırın başındaki kutuyla birden fazla adım seçilir. **Seçilenleri çalıştır (n)** ya da
    **Ctrl+Enter** bunları sırayla çalıştırır. Çift tıklama tek adımı çalıştırır.
- **Üst çubuk:** Seçilenleri çalıştır, **Tam hat**, **Yapay zekâ hattı**, **Durdur** ve "hata
  olursa sonraki adımlarla sürdür" anahtarı.

### İlerleme, hatalar ve sonuçlar

- **İlerleme paneli** (yalnız çalışırken):
  - Çalışan adım, adımın yüzdesi ve işlenen/toplam sayısı (ör. %47,3 · 946/2.000), parça no.
  - **Kalan süre tahmini:** şimdiye kadarki hıza göre hesaplanır.
  - Genel yüzde, geçen süre, hata ve uyarı sayaçları. Pencere başlığında da yüzde görünür.
- **Hatalar ve uyarılar:** araç çıktısındaki hata dökümleri, `[HATA]` satırları, çıkış kodları,
  açılamayan sayfalar. Çift tıklayınca çalışma kaydında o satıra gidilir.
- **Çalışma kaydı:** canlı çıktı; hata satırları kırmızı, uyarılar sarı. Kayıtta arama yapılabilir.
- **Son çalışma:** bitince kendiliğinden açılır. Her adımın durumu, süresi, hata/uyarı sayısı,
  **ürettiği çıktı ve raporlar** ve kayıt dosyası; çift tıklayınca açılır.
- **Hata ayıklama:**
  - Başarısız bir adımın son satırları ve kayıt dosyasının yolu kayda yazılır.
  - Ayarlar > Genel > **Ayrıntılı kayıt** açıksa komut ayrıntıları da yazılır ve Bologna `-v`
    ile çalışır.
  - API anahtarları kayda asla açık yazılmaz.

Her çalışmanın tam kaydı `ciktilar/<profil>/merkez_kayitlari/` altındadır. **Durdur** önce aracın
kısmi sonucu kaydetmesine izin verir, sonra tarayıcılar dahil tüm alt süreçleri kapatır. Araçların
çoğu aynı adım yeniden çalıştırılınca kaldığı yerden devam eder.

---

## 3. Yeni bir site eklemek

1. Sol menüden **Yeni site ekle**: başlangıç adresi (ör. `https://www.ornek.edu.tr/`) ve ad.
   Çıktılar `ciktilar/<profil>/` altında toplanır, diğer sitelerin verileri etkilenmez.
2. **Ayarlar > Site profili**'nde gerekirse düzenleyin:
   - **Keşif kuralları:**
     - Linkler JavaScript ile üretiliyorsa (SPA) "Tarayıcıyla keşfet"i açın.
     - Sonsuz kombinasyon üreten adresleri **hariç desenler**le dışarıda bırakın, ör. `/arama`.
     - Gereksiz sorgu parametrelerini **silinecek parametreler**e ekleyin, ör. `sort`.
     - Sunucuyu yormamak için **saniyede istek** değerini düşük tutun.
   - **Tarayıcı dili ve User-Agent.**
   - **Yapay zekâ talimatı:** sitenin İngilizce tanımı (ör. `an e-commerce website`) ve dili.
   - **Bologna:** OİBS kullanan başka bir üniversitenin Bologna adresi.
3. Ana sayfadaki yol haritasını izleyin: önce **Site keşfi**, sonra **Deneme testi**, sonra
   **Tam hat**.

---

## 4. Görsel denetim: yapay zekâ, doğrulama ve düzeltme

Görsel denetim, [gorsel-denetim](https://github.com/mehmetfatihvar/gorsel-denetim) reposunda
geliştirilen araç zinciridir; programda iki sayfaya ayrılır.

**Yapay zekâ denetimi (1-6):**
1. Ekran görüntüleri kodla taranır.
2. Temsilciler seçilir ve sona kadar kaydırılarak yeniden çekilir.
3. Modeller dilimlere bakar, hakem model anlaşmazlıkları çözer.
4. Modellerin isabeti ölçülür.
5. Görünen metinde kodlama hataları aranır.
6. Ekran görüntüsü kesitli son rapor üretilir.

**Doğrula ve düzelt (7-10):**

| Aşama | Ne yapar |
|---|---|
| 7. Canlı doğrulama | Bulgu olan sayfaları yeniden açıp DOM'da ölçer: DOGRULANDI / GORULMEDI / ELLE. Taşmada sayfa gerçekten yana kaymıyorsa yanlış alarm sayar; hatayı üreten öğeyi ve kaç sayfayı etkilediğini çıkarır (`kok_neden.csv`). Yapay zekâ hattının son adımıdır. |
| 8. Etiketleme | Ölçülemeyen ve yanlış alarm sayılan bulgularla bir örneklemi tarayıcıda açılan sayfada toplar (`1` Gerçek, `2` Yanlış, `3` Emin değilim). "CSV indir" ile kaydedilen `etiketler.csv` 8b adımıyla işlenir; tür başına elle ölçülmüş isabet çıkar. |
| 9. CSS denemesi | Önerilen CSS'i canlı sayfalara (yalnız tarayıcı sekmesine) ekleyip yeniden ölçer: düzelen, kalan, yeni bozulan. |
| 10. Otomatik taşma düzeltme | **Her sitede**: yana kaydıran öğeyi türüne göre sınıflandırıp sitenin kendi sınıflarıyla CSS kuralı üretir, ekleyip ölçer, etkisizse güçlendirir. Çıktı: `oneri.css` ve önce/sonra görüntüleri. |

Site hiçbir aşamada değişmez. 9. aşamada denenen CSS, Ayarlar'da verilen dosyadır. Ayar boşsa
10. aşamanın önerisi kullanılır, o da yoksa ÖİDB için hazırlanmış `tools/visual_audit/oneri.css`.

**gorsel-denetim'den güncelleme:** `tools/visual_audit/` ile `gorsel-denetim/denetim/`, ve
`tools/tester_v3_evidence.py` ile `gorsel-denetim/cekim/tester.py` aynı araçlardır. Güncellerken
iki tarafın değişiklikleri üç yönlü birleştirilir (`git merge-file`). Program için eklenen
seçenekler (site adı ve tanımı, OpenAI uyumlu sağlayıcı ...) korunur; sözleşme testleri
eksikleri yakalar.

---

## 5. Yapay zekâ sağlayıcıları ve modeller

Ayarlar > **Yapay zekâ, Bologna, genel** sekmesinde anahtarlar, adresler ve modeller girilir.
**Tarayan modeller** ve **hakem modeli** alanları şu adları alır:

| Yazım | Sağlayıcı | Gerekenler |
|---|---|---|
| `claude` veya `claude:<model>` | Anthropic | Anthropic anahtarı |
| `gemini` veya `gemini:<model>` | Google Gemini / Gemma | Gemini anahtarı |
| `openai:<model>` | **OpenAI uyumlu her servis**: OpenAI, OpenRouter, Groq, Mistral, Together, LM Studio, vLLM | Adres ve gerekirse anahtar |
| `ollama:<model>` | Yerel Ollama | Ollama adresi |

**Varsayılanlar, görsel denetimde fiilen kullanılan modellerdir:**

| Görev | Model |
|---|---|
| Ana tarama | `gemini:gemma-4-31b-it` |
| Hakem | `gemini:gemini-3.5-flash-lite` (tür bazlı örneklem) |
| Yerel model | `qwen2.5vl:3b` |

Yeni bir servis için kod değişikliği gerekmez. **Hazırlık > Yapay zekâ sağlayıcılarını dene**
her sağlayıcıya bağlanıp kullanılabilir modelleri listeler ve ayarlardaki model adını doğrular.

API anahtarları varsayılan olarak **diske yazılmaz**. "Anahtarları diske kaydet" işaretlenirse
`ayarlar.json` dosyasına yazılır; bu dosya git'e girmez.

---

## 6. Komut satırı

Arayüz açmadan (sunucuda, zamanlanmış görevde):

```bash
python web_denetim.py --liste                  # adımlar
python web_denetim.py --goster tam_test        # çalışacak komutlar (çalıştırmaz)
python web_denetim.py --calistir deneme        # bir veya birkaç adım
python web_denetim.py --calistir tam-hat       # önerilen tam hat
python web_denetim.py --calistir ai-hatti      # yapay zekâ hattı
python web_denetim.py --durum                  # özet
python web_denetim.py --profiller              # profiller
python web_denetim.py --yeni-profil "Örnek Üniversite" https://www.ornek.edu.tr/
python web_denetim.py --profil ornek-universite --calistir kesif deneme
```

Kurulumdan sonra `python` yerine `.venv\Scripts\python` (Linux/macOS: `.venv/bin/python`) ya da
`./baslat.sh --liste` kullanın.

---

## 7. Klasörler ve çıktılar

```
web-denetim-merkezi/
├── BASLAT.bat, KURULUM.bat        Windows
├── baslat.sh, kurulum.sh          Linux / macOS
├── web_denetim.py                 Giriş noktası (arayüz + komut satırı)
├── requirements.txt
├── merkez/                        Program
│   ├── adimlar.py                 Her işin komut karşılığı (tek kaynak)
│   ├── ayarlar.py                 Profil + genel ayarlar, klasör düzeni
│   ├── calistirici.py             Sırayla çalıştırma, canlı çıktı, durdurma, kayıt
│   ├── izleme.py                  Çıktıdan ilerleme, kalan süre, hata/uyarı
│   ├── durum.py                   Özet sayılar, ana sayfa kutucukları, yol haritası
│   ├── ortam.py                   Kurulum denetimi (paketler, Chromium, Go, Docker)
│   ├── saglayicilar.py            Yapay zekâ sağlayıcı testi
│   ├── teslim.py                  TESLIM paketi
│   ├── tema.py                    Açık/karanlık tema
│   └── arayuz.py                  Masaüstü arayüz
├── tools/                         Araçlar (tek başına da çalışır)
│   ├── tester_v3_evidence.py      Kanıtlı tarayıcı testi, belge/link/görsel denetim
│   ├── kesif.py                   Genel site keşfi
│   ├── cluster_templates.py       Şablon kümeleme
│   ├── verify_routes.py, verify_clicks.py   Kırık sayfa doğrulama
│   ├── visual_ai_review.py        Yerel model (Ollama) incelemesi
│   └── visual_audit/              Görsel denetim (gorsel-denetim/denetim): tarama, analiz, isabet,
│                                  metin, rapor, dogrulama, etiketle, css_deneme, oto_duzelt
├── bologna-scraper/               OİBS Bologna → PostgreSQL (Go)
├── profiller/                     Site profilleri (meu-oidb.json hazır)
├── data/meu-oidb/                 ÖİDB site haritası (17.394 sayfa) ve şablon kümeleri
├── tests/                         Birim ve sözleşme testleri
└── ciktilar/<profil>/             Bütün çıktılar (git'e girmez)
    ├── kesif/site_haritasi.json
    ├── deneme_output/, test_output/          report.html, report.xlsx, screenshots/
    ├── denetim/, linkdenetim/, gorsel/       Belge, link, görsel denetim
    ├── gorsel_ai/, yeniden_cekim/
    ├── visual_audit/denetim_cikti/           Piksel tarama, ai_v2/, rapor/
    ├── visual_audit/dogrulama_cikti/, etiket/, css_cikti/, oto_cikti/   Doğrula ve düzelt
    ├── dogrulama/, dogrulama_css/            Doğrulama çekimleri
    ├── routes_verification.csv, clicks_verification.csv
    ├── merkez_kayitlari/                     Her çalışmanın kaydı
    └── TESLIM/index.html                     Teslim paketi
```

---

## 8. Geliştirme

- **Yeni araç:** `merkez/adimlar.py`'deki listeye bir `Adim` eklemek yeterlidir. Arayüz, komut
  satırı, durum ekranı ve kayıtlar yeni adımı kendiliğinden kullanır.
- **Yeni ayar:** `merkez/ayarlar.py`'ye varsayılanıyla, `merkez/arayuz.py`'deki form listesine de
  bir satır eklenir.
- **Testler** yalnız standart kütüphaneyle çalışır:

  ```bash
  python -m unittest discover -s tests -v
  cd bologna-scraper && go test ./...
  ```

  **Sözleşme testleri**, programın araçlara gönderdiği her seçeneğin (`--site-adi`,
  `--openai-url` ...) aracın kodunda tanımlı olduğunu denetler. Araçlar, örneğin görsel
  denetim, güncellendiğinde uyumsuzluk burada yakalanır. GitHub Actions testleri Windows ve
  Linux'ta, Python 3.9 ve 3.12 ile çalıştırır.
