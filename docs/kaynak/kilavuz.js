// Web Denetim Merkezi — Kullanım Kılavuzu (docx). Kullanım: node kilavuz.js <cikti.docx> [sayfalar.json]
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, HeadingLevel, LevelFormat, PageBreak, Header, Footer, PageNumber,
  BorderStyle, Bookmark, InternalHyperlink, PositionalTab, PositionalTabAlignment,
  PositionalTabRelativeTo, PositionalTabLeader, TableLayoutType, Tab, TabStopType, LeaderType, LineRuleType,
} = require("docx");

const KOK = __dirname;
const VERI = JSON.parse(fs.readFileSync(path.join(KOK, "veri.json"), "utf8"));
const CIKTI = process.argv[2] || path.join(KOK, "KULLANIM_KILAVUZU.docx");
const SAYFALAR = process.argv[3] && fs.existsSync(process.argv[3]) ? JSON.parse(fs.readFileSync(process.argv[3], "utf8")) : {};

const YAZI = "Arial", KOD = "Courier New";
const MAVI = "1F4E79", ACIK = "EAF1F8", GRI = "F2F2F2", KENAR = "BFBFBF";
const GENISLIK = 9638;                    // A4, 2 cm kenar boşlukları (DXA)

// ------------------------------------------------------------------ yardımcılar
// Satır içi biçim: **kalın**, `kod`
function parcala(metin, temel = {}) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let son = 0, m;
  while ((m = re.exec(metin))) {
    if (m.index > son) runs.push(new TextRun({ text: metin.slice(son, m.index), ...temel }));
    const p = m[0];
    if (p.startsWith("**")) runs.push(new TextRun({ text: p.slice(2, -2), bold: true, ...temel }));
    else runs.push(new TextRun({ text: p.slice(1, -1), font: KOD, size: 19, ...temel }));
    son = m.index + p.length;
  }
  if (son < metin.length) runs.push(new TextRun({ text: metin.slice(son), ...temel }));
  return runs;
}

const icerik = [];
const basliklar = [];      // içindekiler için: [seviye, metin, yerimi]
let yerimiNo = 0;

function baslik(seviye, metin, yeniSayfa = false) {
  const ad = `b${++yerimiNo}`;
  basliklar.push([seviye, metin, ad]);
  icerik.push(new Paragraph({
    heading: [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][seviye - 1],
    pageBreakBefore: yeniSayfa,
    children: [new Bookmark({ id: ad, children: [new TextRun(metin)] })],
  }));
}
const H1 = (m) => baslik(1, m, true);
const H2 = (m) => baslik(2, m);
const H3 = (m) => baslik(3, m);
const P = (m, ek = {}) => icerik.push(new Paragraph({ children: parcala(m), spacing: { after: 120 }, ...ek }));
const madde = (liste, ref = "madde") => liste.forEach((m) =>
  icerik.push(new Paragraph({ numbering: { reference: ref, level: 0 }, children: parcala(m), spacing: { after: 60 } })));
let numaraNo = 0;
const sirali = (liste) => {           // her listeye yeni numaralandırma örneği
  const ref = `sira${++numaraNo}`;
  numaraTanimlari.push({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });
  madde(liste, ref);
};
const numaraTanimlari = [];

function kutu(baslikMetni, satirlar, renk = ACIK, kenar = MAVI) {
  const cocuklar = [];
  if (baslikMetni) cocuklar.push(new Paragraph({ children: [new TextRun({ text: baslikMetni, bold: true, color: kenar })], spacing: { after: 60 } }));
  satirlar.forEach((s) => cocuklar.push(new Paragraph({ children: parcala(s), spacing: { after: 60 } })));
  icerik.push(new Table({
    width: { size: GENISLIK, type: WidthType.DXA }, columnWidths: [GENISLIK], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [new TableCell({
      width: { size: GENISLIK, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: renk, color: "auto" },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      borders: { left: { style: BorderStyle.SINGLE, size: 24, color: kenar },
                 top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
                 bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
                 right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" } },
      children: cocuklar })] })],
  }));
  icerik.push(new Paragraph({ children: [], spacing: { after: 60 } }));
}
const not = (s) => kutu("Not", Array.isArray(s) ? s : [s]);
const ipucu = (s) => kutu("İpucu", Array.isArray(s) ? s : [s], "EAF6EC", "2E7D32");
const dikkat = (s) => kutu("Dikkat", Array.isArray(s) ? s : [s], "FDF3E1", "B26A00");

function kod(satirlar) {
  icerik.push(new Table({
    width: { size: GENISLIK, type: WidthType.DXA }, columnWidths: [GENISLIK], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [new TableCell({
      width: { size: GENISLIK, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: GRI, color: "auto" },
      margins: { top: 80, bottom: 80, left: 140, right: 140 },
      borders: { top: { style: BorderStyle.SINGLE, size: 4, color: KENAR }, bottom: { style: BorderStyle.SINGLE, size: 4, color: KENAR },
                 left: { style: BorderStyle.SINGLE, size: 4, color: KENAR }, right: { style: BorderStyle.SINGLE, size: 4, color: KENAR } },
      children: satirlar.map((s) => new Paragraph({ children: [new TextRun({ text: s || " ", font: KOD, size: 17 })], spacing: { after: 0 } })),
    })] })],
  }));
  icerik.push(new Paragraph({ children: [], spacing: { after: 80 } }));
}

function tablo(basliklar_, satirlar, oranlar) {
  const top = oranlar.reduce((a, b) => a + b, 0);
  const gen = oranlar.map((o) => Math.floor((o / top) * GENISLIK));
  gen[gen.length - 1] += GENISLIK - gen.reduce((a, b) => a + b, 0);
  const kenar = { style: BorderStyle.SINGLE, size: 4, color: KENAR };
  const hucre = (metin, i, bas) => new TableCell({
    width: { size: gen[i], type: WidthType.DXA },
    shading: bas ? { type: ShadingType.CLEAR, fill: MAVI, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    borders: { top: kenar, bottom: kenar, left: kenar, right: kenar },
    children: String(metin).split("\n").map((s) => new Paragraph({
      children: bas ? [new TextRun({ text: s, bold: true, color: "FFFFFF", size: 19 })] : parcala(s, { size: 19 }),
      spacing: { after: 20 } })),
  });
  icerik.push(new Table({
    width: { size: GENISLIK, type: WidthType.DXA }, columnWidths: gen, layout: TableLayoutType.FIXED,
    rows: [new TableRow({ tableHeader: true, cantSplit: true, children: basliklar_.map((b, i) => hucre(b, i, true)) }),
           ...satirlar.map((r) => new TableRow({ cantSplit: true, children: r.map((h, i) => hucre(h, i, false)) }))],
  }));
  icerik.push(new Paragraph({ children: [], spacing: { after: 100 } }));
}

let sekilNo = 0;
function gorsel(dosya, aciklama, genislikPx = 620) {
  const yol = path.join(KOK, "img", dosya);
  if (!fs.existsSync(yol)) { P(`[Görsel eksik: ${dosya}]`); return; }
  const veri = fs.readFileSync(yol);
  const w = veri.readUInt32BE(16), h = veri.readUInt32BE(20);           // PNG IHDR
  icerik.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 80, after: 40 },
    children: [new ImageRun({ type: "png", data: veri, transformation: { width: genislikPx, height: Math.round(genislikPx * h / w) },
      altText: { title: aciklama, description: aciklama, name: dosya } })] }));
  icerik.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [new TextRun({ text: `Şekil ${++sekilNo}. `, bold: true, size: 18, color: "595959" }),
               new TextRun({ text: aciklama, italics: true, size: 18, color: "595959" })] }));
}

// ------------------------------------------------------------------ içerik
const ADIM = Object.fromEntries(VERI.adimlar.map((a) => [a.id, a]));
const GRUP = Object.fromEntries(VERI.gruplar);
const CIKTILAR = {
  kurulum: "— (kayıt)", ortam: "— (kayıt)", saglayici: "— (kayıt)",
  kesif: "kesif/site_haritasi.json", kesif_kullan: "— (profil ayarı)",
  deneme: "deneme_output/report.html, report.xlsx, screenshots/",
  tam_test: "test_output/report.html, report.xlsx, summary.txt, results.jsonl, screenshots/",
  hatali_tekrar: "test_output/ (güncellenir)", rapor_yenile: "test_output/report.html, .xlsx, summary.txt",
  belge: "denetim/documents_audit.csv", link: "linkdenetim/broken_links.csv",
  kumeleme: "template_clusters.json, template_representatives.json (site haritasının yanında)",
  gorsel: "gorsel/gorsel_rapor.html, gorsel_denetim.csv",
  rota: "routes_verification.csv", tiklama: "clicks_verification.csv",
  ollama: "gorsel_ai/gorsel_ai_rapor.html, gorsel_ai.csv",
  ai_tarama: "visual_audit/denetim_cikti/tarama.csv, ornekler.csv, ozet.txt",
  ai_temsilci: "visual_audit/temsilci_urls.json", ai_yeniden: "yeniden_cekim/ (screenshots, http_hatali.csv)",
  ai_tahmin: "— (kayıt)", ai_analiz: "denetim_cikti/ai_v2/bulgular.csv, oylama.csv, ozet.txt",
  ai_hakem: "denetim_cikti/ai_v2/ (güncellenir)", ai_isabet: "denetim_cikti/ai_v2/isabet.txt, isabet.csv",
  ai_metin: "visual_audit/metin_kontrol.csv", ai_rapor: "denetim_cikti/rapor/rapor.html",
  gd_dogrulama: "visual_audit/dogrulama_cikti/ozet.txt, sonuc.csv, kok_neden.csv",
  gd_etiket: "visual_audit/etiket/etiketle.html", gd_etiket_ozet: "visual_audit/etiket/etiket_ozet.txt, sonuc_etiketli.csv",
  gd_css: "visual_audit/css_cikti/css_ozet.txt, css_sonuc.csv",
  gd_oto: "visual_audit/oto_cikti/oneri.css, ozet.txt, goruntu/karsilastir.html",
  bologna_db: "— (Docker)", bologna_test: "— (kayıt)", bologna_kesfet: "— (kayıt)", bologna_program: "PostgreSQL",
  bologna_seviye: "PostgreSQL", bologna_tumu: "PostgreSQL", bologna_devam: "PostgreSQL", bologna_istatistik: "— (kayıt)",
  teslim: "TESLIM/index.html, raporlar/, veri/",
};

// ---- 1. Giriş
H1("1. Giriş");
H2("1.1 Program ne yapar?");
P("**Web Denetim Merkezi**, bir web sitesini baştan sona test eden ve denetleyen bir masaüstü programıdır. Sitenin tıklanabilir bütün sayfalarını gerçek bir tarayıcıda açar, her sayfa için ekran görüntüsü kanıtı alır, bulguları raporlar ve bulguların gerçek olup olmadığını ayrıca doğrular. Bütün işler tek pencereden, sırayla ya da tek tek çalıştırılır; uzun işler durdurulup kaldığı yerden sürdürülebilir.");
P("Program şu soruları cevaplar:");
madde([
  "Sitede hangi sayfalar var? (**site keşfi**)",
  "Sayfalar açılıyor mu, hangi sayfalar kırık (4xx/5xx)? Güvenlik başlıkları, Türkçe karakter, erişilebilirlik (alt metin, H1, form etiketi), mobil uyum ve JavaScript hataları nasıl? (**kanıtlı test**)",
  "Belgeler (PDF, Word, Excel) erişilebilir mi, sızdırılmış yerel dosya yolu var mı? Hangi bağlantılar kırık? (**belge ve link denetimi**)",
  "Sayfalarda taşma, kırık görsel, kesik metin, boş render gibi görünüm hataları var mı? (**görsel/UI denetimi** ve **yapay zekâ destekli görsel denetim**)",
  "Bulunan hatalar gerçekten var mı, yoksa yanlış alarm mı? (**doğrulama**, **canlı doğrulama**, **elle etiketleme**)",
  "Taşma hataları hangi CSS ile düzelir, düzeltme başka bir yeri bozar mı? (**CSS denemesi**, **otomatik taşma düzeltme**)",
  "OİBS Bologna Bilgi Paketi verisi veritabanına nasıl aktarılır? (**Bologna**)",
]);
P("Program siteye özgü değildir: **site profilleri** sayesinde her siteye uygulanır. Mersin Üniversitesi ÖİDB sitesi hazır profil olarak gelir. Yapay zekâ sağlayıcıları ve modeller ayarlardan seçilir.");
dikkat("Program siteyi değiştirmez. Testler yalnızca sayfaları okur; CSS denemeleri yalnızca programın açtığı tarayıcı sekmesine uygulanır. Yine de sunucuya istek gönderildiği için eşzamanlılık ve hız ayarlarını sitenin kaldırabileceği düzeyde tutun (önerilen: 4 eşzamanlı sekme).");

H2("1.2 Bu kılavuz nasıl okunur?");
madde([
  "Programı ilk kez kuracaksanız: **2. Kurulum** ve **3. Arayüz**.",
  "Bir siteyi denetleyecekseniz: **4. Site profilleri** ve **5. Önerilen iş akışı**.",
  "Bir adımın ne yaptığını ya da hangi dosyayı ürettiğini arıyorsanız: **6. Adımlar**.",
  "Bir raporun ya da sonucun nasıl okunacağını arıyorsanız: **7. Sonuçları okumak**.",
  "Bir şey ters gittiyse: **12. Sorun giderme**.",
]);

H2("1.3 Temel kavramlar");
tablo(["Kavram", "Anlamı"], [
  ["Site profili", "Bir sitenin bütün ayarları: adres, ad, keşif kuralları, test parametreleri, yapay zekâ talimatındaki site tanımı. Her site için ayrı profil olur; `profiller/<ad>.json` dosyasında durur."],
  ["Site haritası", "Test edilecek sayfaların listesi (JSON, `url_list`). Site keşfi üretir; ÖİDB için hazır gelir."],
  ["Adım", "Programın çalıştırdığı tek bir iş (ör. \"Tüm site kanıtlı testi\"). Her adım bir ya da birkaç aracı çalıştırır ve dosya üretir."],
  ["Hat", "Sırayla çalışan adımlar zinciri. **Tam hat** siteyi baştan sona denetler, **Yapay zekâ hattı** görsel denetimi yapar."],
  ["Şablon / temsilci", "Aynı düzende üretilen sayfalar (ör. bütün haber detayları) bir şablondur. Görsel hatalar şablona bağlı olduğundan her şablondan birkaç temsilci sayfa denetlenir."],
  ["Kanıt", "Her sayfanın masaüstü (1366 px) ve mobil (375 px) tam sayfa ekran görüntüsü."],
  ["Çıktı klasörü", "Bir profilin bütün çıktılarının yazıldığı klasör: `ciktilar/<profil>/`."],
  ["Teslim paketi", "Bütün rapor ve verilerin anlaşılır adlarla toplandığı `TESLIM/` klasörü ve içindekiler sayfası."],
], [1, 3.4]);

// ---- 2. Kurulum
H1("2. Kurulum");
H2("2.1 Gereksinimler");
tablo(["Yazılım", "Gerekli mi?", "Ne için"], [
  ["Python 3.9 veya üstü", "Evet", "Programın ve bütün araçların çalışması. python.org'dan kurulan Python, arayüz için gereken Tkinter'ı da içerir."],
  ["İnternet bağlantısı", "Kurulumda evet", "Python paketleri ve Chromium tarayıcısı indirilir (yaklaşık 300 MB)."],
  ["Disk alanı", "Evet", "Program ve paketler ~1 GB. Ekran görüntüleri site büyüklüğüne bağlıdır: ÖİDB'nin tamamı (17.394 sayfa) için ~8–10 GB."],
  ["Docker Desktop", "Yalnız Bologna için", "Bologna'nın PostgreSQL veritabanı ve tarayıcısı Docker ile çalışır."],
  ["Go 1.22+ ve PostgreSQL", "Yalnız Bologna için, Docker yerine", "Bologna'yı Docker olmadan çalıştırmak için."],
  ["Yapay zekâ API anahtarı", "Yalnız yapay zekâ adımları için", "Ör. Google Gemini (ücretsiz katman yeterli). Yerel Ollama ile anahtarsız da çalışır."],
  ["Ollama", "İsteğe bağlı", "Yapay zekâ incelemesini kendi bilgisayarınızda, ücretsiz ve verisiz-dışarı çalıştırmak için."],
], [1.3, 1.1, 3]);

H2("2.2 Windows'ta kurulum");
sirali([
  "Python'u kurun: https://www.python.org/downloads/ adresinden Python 3.9 veya üstünü indirin. Kurulumun ilk ekranında **\"Add python.exe to PATH\"** kutusunu işaretleyin.",
  "Programı indirin: `git clone https://github.com/mehmetfatihvar/web-denetim-merkezi.git` ya da GitHub'da **Code > Download ZIP** ile indirip bir klasöre açın.",
  "Klasördeki **BASLAT.bat** dosyasına çift tıklayın. İlk açılışta **KURULUM.bat** kendiliğinden çalışır: Python'u bulur, sürümünü denetler, klasörün içinde ayrı bir sanal ortam (`.venv`) kurar, paketleri ve Chromium tarayıcısını indirir. Birkaç dakika sürer.",
  "Kurulum bitince program açılır. Sonraki açılışlarda yalnızca **BASLAT.bat** yeterlidir.",
]);
ipucu("Program bilgisayardaki diğer Python kurulumlarına dokunmaz; her şey klasörün içindeki `.venv` sanal ortamına kurulur. Programı kaldırmak için klasörü silmek yeterlidir.");
dikkat("Klasörü OneDrive, Dropbox ya da Masaüstü gibi eşitlenen bir yere koymayın: binlerce ekran görüntüsünün eşitlenmesi hem yavaşlatır hem kotayı doldurur.");

H2("2.3 Linux ve macOS'ta kurulum");
kod([
  "git clone https://github.com/mehmetfatihvar/web-denetim-merkezi.git",
  "cd web-denetim-merkezi",
  "./baslat.sh          # ilk açılışta ./kurulum.sh kendiliğinden çalışır",
]);
P("Debian/Ubuntu'da arayüz ve sanal ortam için şu paketler gerekebilir: `sudo apt install python3-tk python3-venv`. macOS'ta Homebrew Python kullanıyorsanız: `brew install python-tk`.");

H2("2.4 İlk açılışta ortam kontrolü");
P("Program her açılışta, araçları çalıştıracak Python'da gerekli paketlerin ve Chromium tarayıcısının kurulu olup olmadığını arka planda denetler. Eksik varsa ana sayfanın en üstünde bir uyarı kartı çıkar:");
gorsel("16_kurulum_uyarisi.png", "Kurulum eksikse ana sayfada çıkan uyarı ve \"Bağımlılıkları kur\" düğmesi");
P("**Bağımlılıkları kur** düğmesi eksikleri kurar. Ayrıntılı döküm için **Hazırlık > Ortam kontrolü** adımını çalıştırın: her paket, Chromium, Go ve Docker için kurulu/eksik bilgisi çalışma kaydına yazılır.");

H2("2.5 Güncelleme");
sirali([
  "Programı kapatın.",
  "Klasörde `git pull` çalıştırın (ZIP ile indirdiyseniz yeni ZIP'i aynı klasörün üzerine açın; `ciktilar/`, `ayarlar.json` ve kendi profilleriniz korunur).",
  "**KURULUM.bat**'ı (Linux/macOS: `./kurulum.sh`) bir kez çalıştırın; yeni paketler varsa kurulur.",
]);

// ---- 3. Arayüz
H1("3. Arayüz");
H2("3.1 Genel görünüm");
P("Pencere üç bölümden oluşur: solda **menü**, sağda seçilen **sayfa**, altta **ilerleme paneli** ile **çalışma kaydı / hatalar / son çalışma** sekmeleri. Üst kısımda sayfa başlığı ve çalıştırma düğmeleri bulunur. Sayfa ile alt panel arasındaki çizgi sürüklenerek alanlar büyütülüp küçültülebilir.");
gorsel("02_ana_sayfa.png", "Ana sayfa: özet kutucukları, yol haritası ve rapor kısayolları");

H2("3.2 Sol menü");
madde([
  "**Site profili:** hangi sitenin denetleneceği. Açılır listeden seçilir; **+ Yeni site ekle** yeni profil oluşturur (bkz. 4.2).",
  "**Sayfalar:** Ana sayfa; adım sayfaları (Hazırlık, Web testi, Denetimler, Doğrulama, Yapay zekâ denetimi, Doğrula ve düzelt, Bologna, Teslim); Raporlar ve özet; Ayarlar.",
  "**Tema düğmesi** (en altta): açık ve karanlık tema arasında geçiş. Seçim hatırlanır.",
]);

H2("3.3 Üst çubuk");
tablo(["Düğme", "Ne yapar"], [
  ["► Seçilenleri çalıştır (n)", "Adım listelerinde işaretlenen adımları programdaki doğal sırayla çalıştırır. Parantezdeki sayı seçili adım sayısıdır. Kısayol: **Ctrl+Enter**."],
  ["Tam hat", "Siteyi baştan sona denetleyen önerilen sırayı çalıştırır: (harita yoksa site keşfi) → tüm site testi → belge → link → şablon kümeleme → görsel → kırık sayfa doğrulama → buton tıklama doğrulama → teslim. Başlamadan önce listeyi gösterip onay ister."],
  ["Yapay zekâ hattı", "Görsel denetimin 1–7. aşamalarını sırayla çalıştırır (bkz. 6.5)."],
  ["■ Durdur", "Çalışan adımı durdurur. Araç önce kısmi sonucunu kaydeder; sonra tarayıcılar dahil bütün alt süreçler kapatılır. Sıradaki adımlar çalışmaz."],
  ["Hata olursa sonraki adımlarla sürdür", "Kapalıyken bir adım başarısız olursa sonraki adımlar çalışmaz. Açıkken sıradaki adımlarla devam edilir."],
], [1.4, 4]);

H2("3.4 Ana sayfa");
madde([
  "**Özet kutucukları:** site haritasındaki sayfa sayısı, test edilen sayfa ve kapsam, kırık sayfa (4xx/5xx), kırık bağlantı, görsel kusur, kesin yapay zekâ bulgusu. Yalnızca üretilmiş çıktılar için kutucuk görünür.",
  "**Yol haritası:** önerilen iş sırası. Tamamlanan aşamalar ✓ ile işaretlidir; sıradaki aşama ► ile vurgulanır ve **Sıradaki: çalıştır** düğmesiyle tek tıkla başlatılır. Bir aşama yarım kalmışsa (ör. \"2/4 adım\") yalnızca eksik adımları çalışır.",
  "**Raporlar:** üretilmiş raporların kısayolları; henüz üretilmemiş raporların düğmesi pasiftir.",
]);

H2("3.5 Adım sayfaları");
P("Her adım sayfasında solda adımların **listesi**, sağda seçili adımın **ayrıntı kartı** vardır.");
gorsel("03_adim_sayfasi.png", "Web testi sayfası: adım listesi ve seçili adımın ayrıntı kartı");
madde([
  "**Liste sütunları:** seçim kutusu, adım adı, tahmini süre, durum. Durum; son çıktının zamanını, çalışırken canlı yüzdeyi (● %45), bitince sonucu (✓ Başarılı / ✗ Başarısız) gösterir.",
  "**Seçmek:** satırın başındaki kutuya tıklayın ya da satırdayken **boşluk** tuşuna basın. Birden fazla sayfadan adım seçilebilir; seçim sayfalar arasında korunur.",
  "**Çalıştırmak:** tek bir adımı satıra çift tıklayarak ya da kartın **► Çalıştır** düğmesiyle; seçilenleri üst çubuktan.",
  "**Ayrıntı kartı:** adımın açıklaması, ürettiği dosyalar (✓ var / ○ yok), **Çıktıyı aç**, **Klasörü aç** ve **Çalışacak komutu kayda yaz** (adımı çalıştırmadan hangi komutun çalışacağını gösterir).",
]);
gorsel("04_secim.png", "Birden fazla adım seçildiğinde üstteki düğme seçim sayısını gösterir");

H2("3.6 Alt panel: ilerleme, kayıt, hatalar, son çalışma");
H3("İlerleme paneli");
P("Bir çalışma başlayınca alt panelde iki ilerleme çubuğu görünür:");
madde([
  "**Bu adım:** çalışan adımın yüzdesi, işlenen/toplam sayısı (ör. 946/2.000), parçalı testte kaçıncı parça olduğu ve **kalan süre tahmini**. Tahmin son 10 dakikadaki hıza göre yapılır, sunucu yavaşlar ya da hızlanırsa kendini günceller. Sayfalar eşzamanlı test edildiği için sayı, listedeki sıra değil bitirilen sayfa sayısıdır; tam testte zaten yapılmış olduğu için atlanan parçalar hız hesabına katılmaz.",
  "**Toplam:** seçilen bütün adımların genel yüzdesi.",
  "Sağ üstte **geçen süre**, kırmızı **Hata** ve sarı **Uyarı** sayaçları. Sayaçlara tıklamak hata listesini açar. Pencere başlığında da genel yüzde görünür.",
]);
gorsel("05_calisirken.png", "Tüm site testi çalışırken: adım ve toplam ilerlemesi, kalan süre, canlı kayıt");
H3("Çalışma kaydı");
P("Araçların canlı çıktısıdır. Hata satırları kırmızı, uyarılar sarı görünür. **Kayıtta ara** ile metin aranır. **Yeni satırları takip et** kapatılırsa eski satırlar kaymadan okunur. Her adımın tam kaydı ayrıca `ciktilar/<profil>/merkez_kayitlari/` klasörüne tarih ve adım adıyla yazılır (**Kayıt klasörü** düğmesi).");
H3("Hatalar ve uyarılar");
P("Araç çıktısında yakalanan hatalar (Python hata dökümü, `[HATA]` satırları, sıfır olmayan çıkış kodu, bulunamayan program) ve uyarılar (`[!]` satırları, açılamayan ya da zaman aşımına uğrayan sayfa) saat ve adım adıyla listelenir. Satıra **çift tıklamak** çalışma kaydında o satıra gider ve vurgular. **Panoya kopyala** listeyi destek istemek için kopyalar.");
gorsel("07_hatalar.png", "Hatalar ve uyarılar sekmesi");
H3("Son çalışma");
P("Bir çalışma bitince kendiliğinden açılır: her adımın durumu, süresi, hata/uyarı sayısı, **ürettiği çıktı ve raporlar** ve kayıt dosyası. Bir satıra çift tıklamak dosyayı açar; **Bulunduğu klasör** klasörü açar; **Teslim paketi oluştur** paketi hazırlar.");
gorsel("06_son_calisma.png", "Son çalışma sekmesi: adımlar, süreler ve üretilen dosyalar");

H2("3.7 Tema ve kısayollar");
P("Sol alttaki düğme açık ve karanlık tema arasında geçiş yapar. Görünüm `sv-ttk` paketiyle Windows 11 tarzındadır; paket yoksa aynı renklerle temel tema kullanılır.");
gorsel("15_karanlik_tema.png", "Karanlık tema", 520);
tablo(["Kısayol", "İşlev"], [
  ["Ctrl+Enter", "Seçilen adımları çalıştır"],
  ["Boşluk (adım listesinde)", "Satırdaki adımı seç / seçimi kaldır"],
  ["Çift tıklama (adım listesinde)", "Adımı tek başına çalıştır"],
  ["F5", "Durum ve özetleri yenile"],
  ["Enter (arama kutusunda)", "Kayıtta önceki eşleşmeyi bul"],
], [1.6, 3]);

// ---- 4. Site profilleri
H1("4. Site profilleri");
P("Profil, bir sitenin bütün ayarlarını tutar. Profil değiştirmek o sitenin çıktılarını ve ayarlarını getirir; yapay zekâ anahtarları gibi genel ayarlar bütün profillerde ortaktır.");
H2("4.1 Hazır ÖİDB profili");
P("`meu-oidb` profili Mersin Üniversitesi ÖİDB ön-prodüksiyon sitesi (`https://193.255.182.40/`) içindir. 17.394 sayfalık site haritası ve şablon kümeleri `data/meu-oidb/` klasöründe hazır gelir; bu yüzden **keşif adımını atlayıp doğrudan teste geçebilirsiniz**. Site kurum ağındadır; dışarıdan erişim için VPN gerekebilir.");
H2("4.2 Yeni site eklemek");
sirali([
  "Sol menüde **+ Yeni site ekle**'ye basın.",
  "**Başlangıç adresi** (ör. `https://www.ornek.edu.tr/`), **profil adı** ve raporlarda görünecek **site adı**nı girip **Oluştur**'a basın.",
  "Yeni profil seçili olarak açılır. Çıktıları `ciktilar/<profil>/` altında toplanır; diğer sitelerin verileri etkilenmez.",
  "Ana sayfadaki yol haritasını izleyin: önce **Site keşfi**, sonra **Deneme testi**, sonra **Tam hat**.",
]);
gorsel("14_yeni_site.png", "Yeni site ekleme penceresi", 520);
H2("4.3 Profil ayarlarını siteye göre düzenlemek");
P("**Ayarlar > Site profili** sekmesindeki ayarların tam listesi 9. bölümdedir. En çok ihtiyaç duyulanlar:");
madde([
  "**Keşif kuralları:** Site linkleri JavaScript ile üretiyorsa (SPA: React, Vue …) **Tarayıcıyla keşfet**'i açın. Filtre, sıralama, takvim gibi sonsuz kombinasyon üreten adresleri **Hariç desenler**'e yazın (ör. `/arama /etiket/ /takvim`). Gereksiz sorgu parametrelerini (ör. `sort filtre sayfa_boyutu`) **Silinecek sorgu parametreleri**'ne ekleyin. **Yol başına sorgu varyasyonu** ikinci bir güvencedir.",
  "**Saniyede istek ve eşzamanlılık:** sunucuyu yormamak için düşük tutun. Zaman aşımı hataları artarsa eşzamanlılığı düşürün.",
  "**Tarayıcı dili ve User-Agent:** testin hangi dilde ve hangi kimlikle yapılacağı.",
  "**Yapay zekâ talimatı:** sitenin İngilizce tanımı (ör. `an e-commerce website`) ve dili (ör. `German`). Modele verilen talimat bunlarla kurulur.",
]);
P("Değişikliklerden sonra **Kaydet**'e basın. Kaydedilmeyen değişiklikler yine de o oturumdaki çalışmalarda kullanılır; **Değişiklikleri geri al** formu kayıtlı haline döndürür.");
H2("4.4 Profil dosyaları");
P("Profiller `profiller/<ad>.json`, genel ayarlar `ayarlar.json` dosyasındadır. Bir profili başka bir bilgisayara taşımak için profil dosyasını kopyalamak yeterlidir; yollar program klasörüne göreli tutulur. `ayarlar.json` ve `ciktilar/` git'e girmez.");

// ---- 5. İş akışı
H1("5. Önerilen iş akışı");
H2("5.1 Yol haritası");
P("Ana sayfadaki yol haritası şu sırayı önerir. Her aşama bir öncekinin çıktısını kullanır:");
tablo(["#", "Aşama", "Neden bu sırada?"], [
  ["1", "Site haritası (keşif)", "Test edilecek sayfaların listesi olmadan hiçbir adım çalışmaz."],
  ["2", "Deneme testi", "İlk 50 sayfayla bağlantıyı, raporu ve süreyi görürsünüz. Sorun varsa tüm siteye geçmeden fark edilir."],
  ["3", "Tüm site testi", "Bütün sayfalar test edilir, ekran görüntüleri alınır. Görsel ve yapay zekâ denetimi bu görüntüleri kullanır."],
  ["4", "Denetimler", "Belge, kırık link ve şablon bazlı görsel kusur denetimi."],
  ["5", "Doğrulama", "Kırık görünen sayfalar doğrudan açılarak ve butonlara tıklanarak teyit edilir."],
  ["6", "Yapay zekâ görsel denetimi", "Kodla ölçülemeyen görsel hatalar (üst üste binme, eksik veri, bozuk karakter …) için."],
  ["7", "Doğrula ve düzelt", "Bulgular canlı sitede doğrulanır; taşma için CSS düzeltme önerisi üretilir."],
  ["8", "Teslim paketi", "Bütün çıktılar tek klasörde toplanır."],
], [0.3, 1.6, 4]);

H2("5.2 Hatlar");
P("**Tam hat** adımları:");
sirali(VERI.tam_hat.map((i) => `${ADIM[i].ad}`));
P("Site haritası henüz yoksa (yeni site) tam hat **site keşfi** ile başlar.");
P("**Yapay zekâ hattı** adımları:");
sirali(VERI.ai_hatti.map((i) => `${ADIM[i].ad}`));

H2("5.3 Uzun işler: durdurma ve kaldığı yerden devam");
madde([
  "Tüm site testi büyük sitelerde saatler sürer; bilgisayarı uyku moduna almayın, şarja takın.",
  "**Durdur** ile ya da program kapanınca yarıda kalan adımı **yeniden çalıştırmanız yeterlidir**: test, keşif, yapay zekâ analizi ve Bologna kaldığı yerden devam eder. Yapılmış sayfalar atlanır.",
  "Tüm site testinde **Tam testi sıfırdan başlat** (Ayarlar) açıksa önceki sonuçlar silinip baştan başlanır; normalde kapalı tutun.",
  "Ücretsiz Gemini kotası günlük dolarsa yapay zekâ analizi durur; ertesi gün aynı adımı çalıştırın.",
]);

H2("5.4 Örnek senaryolar");
H3("ÖİDB sitesinin tamamını denetlemek");
sirali([
  "Profil: `meu-oidb`. Gerekirse VPN'e bağlanın.",
  "**Web testi > Deneme testi** ile bağlantıyı kontrol edin.",
  "**Tam hat**'ı çalıştırın (harita hazır olduğu için keşif atlanır).",
  "Yapay zekâ anahtarını girip **Yapay zekâ hattı**'nı çalıştırın; kota dolarsa ertesi gün sürdürün.",
  "**Doğrula ve düzelt > 10. Otomatik taşma düzeltme** ile CSS önerisi alın; **Teslim > Teslim paketini oluştur**.",
]);
H3("Yeni bir siteyi ilk kez denetlemek");
sirali([
  "**+ Yeni site ekle** ile profil oluşturun.",
  "**Hazırlık > Site keşfi**'ni çalıştırın; kayıtta \"haritaya N sayfa yazıldı\" satırını kontrol edin. Sayı beklenenden çok büyükse hariç desenleri ve sorgu sınırını ayarlayıp keşfi **Taze** başlatın (aynı adım kaldığı yerden devam eder; baştan başlamak için `ciktilar/<profil>/kesif/` klasörünü silin).",
  "**Deneme testi**, ardından **Tam hat**.",
]);
H3("Yalnızca taşma düzeltme önerisi almak");
P("Herhangi bir site için profil oluşturup doğrudan **Doğrula ve düzelt > 10. Otomatik taşma düzeltme**'yi çalıştırmak yeterlidir. Site haritası yoksa araç sayfaları sitemap.xml'den ya da linkleri izleyerek kendisi bulur. Çıktı `oneri.css` ve önce/sonra görüntüleridir.");
H3("Geliştirici bir düzeltme yaptıktan sonra yeniden kontrol");
madde([
  "Kırık sayfalar için: **Hatalı sayfaları yeniden test et** ve **Kırık sayfa doğrulama**.",
  "Görsel bulgular için: **7. Bulguları canlı sitede doğrula** (eski bulgular yeni ölçümle karşılaştırılır).",
  "Tamamını yeniden ölçmek için: Ayarlar'da **Tam testi sıfırdan başlat**'ı açıp tüm site testini çalıştırın.",
]);

// ---- 6. Adımlar
H1("6. Adımlar");
P("Bu bölüm programdaki bütün adımları sayfa sayfa listeler. Çıktı yolları `ciktilar/<profil>/` klasörüne görelidir.");
const grupAciklama = {
  hazirla: "", hazirlik: "Kurulum, ortam ve sağlayıcı kontrolleri ile sitenin keşfi.",
  web: "Sayfalar gerçek bir Chromium tarayıcıda açılır; her sayfa için HTTP durumu, yüklenme süresi, güvenlik başlıkları, Türkçe karakter, erişilebilirlik, mobil uyum, JavaScript hataları ve formlar ölçülür, masaüstü + mobil ekran görüntüsü alınır.",
  denetim: "Belge erişilebilirliği, bütün bağlantıların sağlığı ve şablon temsilcilerinde görsel/UI kusurları.",
  dogrulama: "Kırık görünen sayfaların gerçekten kırık olduğunun iki bağımsız yolla teyidi.",
  ai: "Ekran görüntüleri kodla taranır, yapay zekâ modellerine dilim dilim sorulur, modeller birbirini ve piksel ölçümünü doğrular, son rapor üretilir.",
  duzeltme: "Bulguların canlı sitede doğrulanması, yanlış alarmların elle ayıklanması ve taşma için CSS düzeltmesinin üretilip denenmesi.",
  bologna: "OİBS Bologna Bilgi Paketi'ni tarayıp ilişkileri koruyarak PostgreSQL'e yazar (bkz. Ek A).",
  teslim: "Bütün çıktıları tek klasörde toplar.",
};
let gNo = 0;
for (const [grup, ad] of VERI.gruplar) {
  H2(`6.${++gNo} ${ad}`);
  if (grupAciklama[grup]) P(grupAciklama[grup]);
  if (grup === "ai") gorsel("09_yapay_zeka.png", "Yapay zekâ denetimi sayfası");
  if (grup === "duzeltme") gorsel("10_dogrula_duzelt.png", "Doğrula ve düzelt sayfası");
  tablo(["Adım", "Ne yapar", "Çıktı", "Süre"],
    VERI.adimlar.filter((a) => a.grup === grup).map((a) => [`**${a.ad}**`, a.aciklama, CIKTILAR[a.id] || "", a.sure || ""]),
    [1.2, 2.7, 1.6, 0.85]);
}

// ---- 7. Sonuçları okumak
H1("7. Sonuçları okumak");
H2("7.1 Kanıtlı test raporu (report.html)");
P("`test_output/report.html` tarayıcıda açılır; filtrelenebilir ve sayfalanabilir bir tablodur. Her satır bir sayfadır; küçük resimlere tıklayınca masaüstü ve mobil ekran görüntüsü açılır. Aynı veriler `report.xlsx` (Excel), `summary.txt` (özet) ve `results.jsonl` (ham veri) dosyalarındadır.");
gorsel("17_test_raporu.png", "Kanıtlı test raporu: özet kutucukları, filtreler ve sayfa başına sonuç");
tablo(["Genel sonuç", "Ne zaman verilir"], [
  ["PASS (geçti)", "Sayfa 200 döndü ve aşağıdaki uyarılardan hiçbiri yok."],
  ["WARN (uyarı)", "Sayfa 200 döndü ama şunlardan en az biri var: alt metni olmayan görsel, H1 eksikliği, bozuk Türkçe karakter şüphesi, JavaScript hatası, görsel kusur."],
  ["FAIL (kaldı)", "Sayfa 200 dışında bir durum döndü (ör. 404, 403, 500) ya da test sırasında sayfa yanıt verdikten sonra hata oluştu."],
  ["ERROR (hata)", "Sayfaya hiç ulaşılamadı (zaman aşımı, bağlantı hatası). Bu sayfalar **Hatalı sayfaları yeniden test et** ile tekrar denenir."],
], [1, 4]);
P("Raporda ayrıca ölçülen her başlık için sütunlar vardır: HTTP durum ve süre, güvenlik başlıkları (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy), Türkçe karakter, erişilebilirlik, mobil uyum (viewport etiketi, 375 px'te görünüm), konsol/JS hataları (React hydration hataları ayrı işaretlenir) ve formlar.");
H2("7.2 Belge ve bağlantı denetimi");
P("`denetim/documents_audit.csv` her belge bağlantısı için bir satırdır; `flag` sütunu:");
tablo(["flag", "Anlamı"], [
  ["erisilebilir", "Belge açılıyor."],
  ["KIRIK/ERISILEMIYOR", "Belge 4xx/5xx dönüyor."],
  ["ULASILAMADI", "Sunucuya ulaşılamadı (zaman aşımı vb.)."],
  ["SIZDIRILMIS YEREL DOSYA YOLU", "Bağlantı bir bilgisayarın yerel diskini gösteriyor (ör. `C:\\Users\\...`): hem kırık hem bilgi sızıntısı."],
], [1.6, 4]);
P("`linkdenetim/broken_links.csv` kırık bağlantıları, bulunduğu sayfayı (`kaynak_sayfa`) ve butonun metnini (`buton_metni`) verir; düzeltme için hangi sayfada hangi linkin değişmesi gerektiği buradan okunur.");
H2("7.3 Görsel/UI kusur raporu");
P("`gorsel/gorsel_rapor.html` şablon özetlidir: bir kusur \"bu düzen ≈N sayfayı etkiliyor\" diye bir kez raporlanır, kusurlu bölge ekran görüntüsünde kırmızı kutuyla işaretlenir.");
gorsel("18_gorsel_rapor.png", "Görsel/UI kusur raporu: şablon özeti ve işaretli kanıt");
tablo(["Kusur türü", "Anlamı", "Öncelik"], [
  ["İçerik ekrandan taşıyor", "Ekranda fiilen çizilen, metin/görsel içeren bir öğe görünür alanı aşıyor; kullanıcı sayfayı yana kaydırmak zorunda kalıyor.", "Yüksek"],
  ["Kırık görsel", "Görsel yüklenmedi.", "Yüksek"],
  ["Boş / çökmüş render", "Sayfa boş ya da içeriksiz çizildi.", "Yüksek"],
  ["Metin kırpılıyor", "Metin kutusuna sığmıyor ve kesiliyor.", "Orta"],
], [1.4, 3.6, 0.7]);
H2("7.4 Kırık sayfa doğrulaması");
tablo(["Dosya ve karar", "Anlamı"], [
  ["routes_verification.csv: GERÇEKTEN KIRIK", "Sayfa doğrudan açıldığında içerik gelmiyor; kırık olduğu kesin."],
  ["… İÇERİK GELİYOR (durum X ama tarayıcıda açılıyor)", "Sunucu hata kodu döndürse de uygulama sayfayı çiziyor; düşük öncelik."],
  ["… ÇALIŞIYOR (200)", "Sayfa artık çalışıyor (düzeltilmiş)."],
  ["clicks_verification.csv: KIRIGA GÖTÜRÜYOR", "Sitedeki butona gerçekten tıklandığında kırık sayfaya gidiliyor."],
  ["… ÇALIŞAN YERE GİDİYOR", "Buton çalışan bir sayfaya gidiyor."],
  ["… LİNK/BUTON YOK, REFERRER AÇILMADI", "Linki içeren sayfa açılamadı ya da link artık yok."],
], [2.2, 3.4]);
H2("7.5 Yapay zekâ görsel denetimi");
madde([
  "**Piksel taraması** (`tarama.csv`, `ozet.txt`): yatay taşma, boş sayfa, anormal boy, eksik masaüstü/mobil eşi ve aynı görünen sayfalar kodla kesin olarak ölçülür.",
  "**Bulgular** (`ai_v2/bulgular.csv`) ve **oylama** (`ai_v2/oylama.csv`): iki model aynı dilimde aynı türü bulduysa **KESİN**, tek model bulduysa **İNCELE**.",
  "**İsabet** (`ai_v2/isabet.txt`): hata türü başına hakem modelin onay oranı; taşmada piksel ölçümüne göre isabet ve yakalama. İlk çalıştırmada bozuk karakterde %82–92, üst üste binmede %57–60 uyum ölçüldü; taşmada yapay zekâ yerine kod ölçümü esas alınır.",
  "**Metin kodlama** (`metin_kontrol.csv`): görünen metinde `?` ile kaybolan Türkçe karakter (Atat?rk), ekrana basılan HTML kodu (`&#39;`), mojibake (`Ã¼`), `�` ve HTML etiketi.",
  "**Son rapor** (`denetim_cikti/rapor/rapor.html`): bütün bunları ekran görüntüsü kesitleriyle tek sayfada toplar.",
]);
H2("7.6 Canlı doğrulama (7. aşama)");
P("`dogrulama_cikti/ozet.txt` her bulgu türü için kararların sayısını, `sonuc.csv` bulgu başına kararı verir:");
tablo(["Karar", "Anlamı"], [
  ["DOGRULANDI", "Aynı hata, aynı cihazda (yapay zekâ bulgusunda aynı dikey bölgede) yeniden ölçüldü. Taşmada ayrıca sayfanın kendisi yana kayıyor."],
  ["GORULMEDI", "Sayfa açıldı ama hata ölçülmedi: düzeltilmiş ya da çekimden kaynaklanmış. Taşmada öğe taşıyor ama sayfa yana kaymıyorsa (kendi kutusunda kayan tablo vb.) yanlış alarm sayılır."],
  ["ELLE", "DOM ile ölçülemeyen tür (üst üste binme, eksik veri …); işaretli görüntüye bakılmalı → etiketleme."],
  ["ACILAMADI", "Sayfa yeniden açılamadı."],
], [1.1, 4.5]);
P("**Kök neden** (`kok_neden.csv`): aynı CSS seçicisinden kaynaklanan taşmalar sayfa sayısıyla listelenir. Üstteki satırlar \"tek düzeltme, çok sayfa\" demektir; geliştiriciye önce bunlar iletilmelidir.");
H2("7.7 Elle etiketleme (8. aşama)");
sirali([
  "**8a. Etiketleme sayfasını oluştur** adımından sonra kartta **Çıktıyı aç** ile `etiketle.html` tarayıcıda açılır.",
  "Her bulgu için eski çekim ile sayfanın şimdiki hali yan yana gösterilir; ekran kenarı kırmızı çizgiyle işaretlidir.",
  "Klavyeyle **1** Gerçek, **2** Yanlış, **3** Emin değilim; **←** **→** ile gezilir. Etiketler tarayıcıda saklanır, sayfa kapanıp açılsa da kaybolmaz.",
  "Bitince **CSV indir** ile `etiketler.csv` kaydedilir (varsayılan: İndirilenler klasörü; başka yere kaydettiyseniz Ayarlar'da yolunu verin).",
  "**8b. Etiketleri işle** tür başına elle ölçülmüş isabeti (`etiket_ozet.txt`) ve her bulguya insan etiketini (`sonuc_etiketli.csv`) üretir.",
]);
H2("7.8 CSS düzeltmesi (9. ve 10. aşamalar)");
madde([
  "**10. Otomatik taşma düzeltme**: sayfayı yana kaydıran öğeyi türüne göre sınıflandırır (uzun metin, tablo, gömülü içerik, sabit genişlikli kutu), sitenin kendi sınıflarıyla CSS kuralı yazar, ekleyip yeniden ölçer, etkisizse güçlendirir. `ozet.txt` tur başına kayan/düzelen/yeni bozulan sayısını, `oneri.css` kuralları (her kuralın üstünde kaç sayfayı düzelttiği), `goruntu/karsilastir.html` önce/sonra görüntülerini verir.",
  "**9. CSS düzeltme önerisini dene**: bir CSS dosyasını (varsayılan: otomatik düzeltmenin önerisi) canlı doğrulamada yana kayan sayfalara ekleyip ölçer. `css_ozet.txt`: düzelen, kalan ve **yeni bozulan** sayfa sayısı.",
]);
dikkat("Ölçüm yalnızca yana kaymayı görür. `oneri.css` geliştiriciye verilmeden önce `karsilastir.html`'deki önce/sonra görüntülerine ve seçicilere bir kez gözle bakılmalıdır. \"Yeni bozulan\" sıfırdan büyükse o sayfalar elle kontrol edilmelidir.");
H2("7.9 Raporlar ve özet sayfası");
P("Menüdeki **Raporlar ve özet** sayfası bütün çıktılardan çıkarılan sayıları tek tabloda gösterir (F5 ile yenilenir) ve raporları açan düğmeleri içerir.");
gorsel("11_raporlar.png", "Raporlar ve özet sayfası");
H2("7.10 Teslim paketi");
P("`TESLIM/` klasöründe `raporlar/` (HTML raporlar, CSS önerisi, son görsel denetim raporu, önce/sonra görüntüleri) ve `veri/` (bütün CSV/XLSX/JSON çıktılar) bulunur; `index.html` bunların açıklamalı listesidir. Ekran görüntüleri büyük olduğu için pakete kopyalanmaz; gerekirse `test_output/screenshots/` ayrıca ZIP'lenir.");

// ---- 8. Yapay zekâ
H1("8. Yapay zekâ ayarları");
H2("8.1 Sağlayıcılar ve model yazımı");
gorsel("13_ayarlar_genel.png", "Ayarlar: yapay zekâ sağlayıcıları ve modeller");
P("Ayarlar > **Yapay zekâ, Bologna, genel** sekmesinde her sağlayıcının anahtarı, adresi ve varsayılan modeli girilir. **Tarayan modeller** (virgülle birden fazla) ve **Hakem modeli** alanları şu yazımları kabul eder:");
tablo(["Yazım", "Sağlayıcı", "Gerekenler"], [
  ["`claude` veya `claude:<model>`", "Anthropic", "Anthropic API anahtarı"],
  ["`gemini` veya `gemini:<model>`", "Google Gemini / Gemma", "Gemini API anahtarı (ücretsiz katman yeterli)"],
  ["`openai:<model>`", "OpenAI uyumlu her servis: OpenAI, OpenRouter, Groq, Mistral, Together, LM Studio, vLLM, Ollama'nın OpenAI ucu", "Adres (listeden seçilir) ve gerekirse anahtar"],
  ["`ollama:<model>`", "Yerel Ollama", "Ollama kurulu ve model indirilmiş olmalı (`ollama pull <model>`)"],
], [1.6, 2.4, 2]);
P("**Hazırlık > Yapay zekâ sağlayıcılarını dene** her sağlayıcıya bağlanır, kullanılabilir modelleri listeler ve ayarlardaki model adının listede olup olmadığını söyler. Yeni bir servis için kod değişikliği gerekmez.");
H2("8.2 Varsayılan modeller");
tablo(["Görev", "Model", "Not"], [
  ["Ana tarama", "`gemini:gemma-4-31b-it`", "Görsel denetimde fiilen kullanılan model; ücretsiz katmanda çalışır."],
  ["Hakem", "`gemini:gemini-3.5-flash-lite`", "Tür bazlı örneklemle (`tur`) modelin isabetini ölçer."],
  ["Yerel model", "`qwen2.5vl:3b`", "Ollama incelemesi. Küçük modeller hataları kaçırabilir; GPU varsa `qwen2.5vl:7b` önerilir."],
], [1, 1.9, 3]);
H2("8.3 Anahtarlar ve güvenlik");
madde([
  "Anahtarlar varsayılan olarak **diske yazılmaz**; yalnızca o oturumda kullanılır. Kalıcı olsun isterseniz **Anahtarları diske kaydet**'i işaretleyin; anahtarlar `ayarlar.json`'a yazılır ve bu dosya git'e girmez.",
  "Anahtarlar araçlara ortam değişkeni olarak geçirilir ve çalışma kaydına hiçbir zaman açık yazılmaz.",
  "Kurum içi bir sitenin ekran görüntüleri bulut modellere gönderilir. Bu kabul edilemiyorsa yerel Ollama ya da kurum içi OpenAI uyumlu bir sunucu kullanın.",
]);
H2("8.4 Kota, hız ve maliyet");
madde([
  "**Dakikada istek sınırı** (varsayılan 8): ücretsiz Gemini katmanının dakikalık sınırına takılmamak için. Ücretli hesapta 0 (sınırsız) yapılabilir.",
  "Günlük kota dolarsa analiz o model için durur; ertesi gün aynı adım kaldığı yerden devam eder.",
  "**3a. Maliyet/süre tahmini** API çağırmadan istek sayısını ve Claude için tahmini maliyeti gösterir. Önce **Sayfa sınırı (deneme)** ile küçük bir tur yapmanız önerilir.",
  "Claude kullanıyorsanız **Claude toplu istek (Batch)** maliyeti yarıya indirir; sonuç genelde bir saat içinde gelir.",
]);
H2("8.5 Modele giden talimat");
P("Her ekran görüntüsü cihaza göre dilimlenir (masaüstü 1024×1024, mobil 375×1334 piksel, görüntü başına en fazla 3 dilim) ve her dilim modele ayrı sorulur. Modele, sitenin tanımını ve dilini içeren İngilizce bir talimat, dilimin cihaz ve konum bilgisi, görüntü ve cevabın uyması gereken JSON şeması gider. Model yalnızca gerçek bir ziyaretçinin fark edeceği görsel hataları, her biri için görünen metni kanıt olarak kopyalayarak raporlar; emin olmadığı şeyi yazmaz. Hata türleri: yatay taşma, üst üste binme, kesik metin, kırık görsel, hizasızlık, düşük kontrast, bozuk karakter, açıklanamayan boşluk, bozuk gezinme, eksik veri, diğer.");
P("Talimattaki site tanımı ve dil **Ayarlar > Site profili > Yapay zekâ talimatı**'ndan değiştirilir. Talimatın tam metni `tools/visual_audit/analiz.py` dosyasındadır.");

// ---- 9. Ayarlar
H1("9. Ayarlar başvurusu");
gorsel("12_ayarlar_site.png", "Ayarlar: site profili");
P("**Site profili** ayarları seçili siteye, **Yapay zekâ, Bologna, genel** ayarları bütün sitelere uygulanır. Varsayılan sütunu yeni bir profilin değerini gösterir; ÖİDB profilinde bazı değerler farklıdır.");
const varsayilanYaz = (v) => v === true ? "açık" : v === false ? "kapalı" : (v === "" || v === null || v === undefined) ? "(boş)" : String(v);
let aNo = 0;
for (const [sekme, bolumler] of [["Site profili", VERI.ayarlar.site], ["Yapay zekâ, Bologna, genel", VERI.ayarlar.genel]]) {
  H2(`9.${++aNo} ${sekme}`);
  for (const [bolum, alanlar] of bolumler) {
    H3(bolum);
    tablo(["Ayar", "Açıklama", "Varsayılan"], alanlar.map(([k, e, t, y, v]) => [
      `**${e}**`, y || "—",
      (k === "python" || k === "cikti_koku" || k === "harita" || k === "site_url" || k === "site_adi") ? "profile göre" :
      (t === "gizli" ? "(boş)" : varsayilanYaz(v))]), [1.6, 3.2, 1.2]);
  }
}

// ---- 10. Komut satırı
H1("10. Komut satırı");
P("Bütün adımlar arayüz açmadan da çalıştırılabilir (sunucuda, zamanlanmış görevde). Kurulumdan sonra Windows'ta `.venv\\Scripts\\python`, Linux/macOS'ta `./baslat.sh` kullanın:");
kod([
  "python web_denetim.py --liste                  # bütün adımlar",
  "python web_denetim.py --goster tam_test        # çalışacak komutlar (çalıştırmaz)",
  "python web_denetim.py --calistir deneme        # bir ya da birkaç adım",
  "python web_denetim.py --calistir tam-hat       # tam hat",
  "python web_denetim.py --calistir ai-hatti      # yapay zekâ hattı",
  "python web_denetim.py --calistir belge link --devam-et   # hata olsa da sürdür",
  "python web_denetim.py --durum                  # çıktılardan özet",
  "python web_denetim.py --profiller              # profiller",
  "python web_denetim.py --yeni-profil \"Örnek Üniversite\" https://www.ornek.edu.tr/",
  "python web_denetim.py --profil ornek-universite --calistir kesif deneme",
]);
P("Adım kimlikleri (`deneme`, `tam_test`, `gd_oto` …) `--liste` çıktısında ve 6. bölümdeki tablolarda adların karşılığıdır. Her araç ayrıca tek başına da çalışır: `python tools/<araç>.py --help`.");

// ---- 11. Klasörler
H1("11. Klasörler ve dosyalar");
kod([
  "web-denetim-merkezi/",
  "├── BASLAT.bat, KURULUM.bat        Windows başlatma ve kurulum",
  "├── baslat.sh, kurulum.sh          Linux / macOS",
  "├── web_denetim.py                 Program (arayüz + komut satırı)",
  "├── ayarlar.json                   Genel ayarlar (git'e girmez)",
  "├── profiller/                     Site profilleri",
  "├── data/meu-oidb/                 ÖİDB site haritası ve şablon kümeleri",
  "├── merkez/                        Programın kendisi",
  "├── tools/                         Araçlar (tek başına da çalışır)",
  "│   ├── tester_v3_evidence.py      Kanıtlı test, belge/link/görsel denetim",
  "│   ├── kesif.py                   Site keşfi",
  "│   └── visual_audit/              Görsel denetim (1-10. aşamalar)",
  "├── bologna-scraper/               Bologna (Go)",
  "├── docs/                          Bu kılavuz (Word ve PDF)",
  "└── ciktilar/<profil>/             Bütün çıktılar (git'e girmez)",
  "    ├── kesif/                     site_haritasi.json",
  "    ├── deneme_output/, test_output/   report.html, report.xlsx, screenshots/",
  "    ├── denetim/, linkdenetim/, gorsel/",
  "    ├── routes_verification.csv, clicks_verification.csv",
  "    ├── yeniden_cekim/, dogrulama/, dogrulama_css/, gorsel_ai/",
  "    ├── visual_audit/              denetim_cikti/, dogrulama_cikti/, etiket/,",
  "    │                              css_cikti/, oto_cikti/, metin_kontrol.csv",
  "    ├── merkez_kayitlari/          Her çalışmanın kaydı",
  "    └── TESLIM/                    Teslim paketi (index.html)",
]);

// ---- 12. Sorun giderme
H1("12. Sorun giderme");
tablo(["Belirti", "Olası neden", "Çözüm"], [
  ["BASLAT.bat açılıp kapanıyor, \"Python bulunamadı\"", "Python kurulu değil ya da PATH'te yok.", "Python'u python.org'dan \"Add python.exe to PATH\" işaretli kurun, BASLAT.bat'ı yeniden çalıştırın."],
  ["Kurulum \"Paketler kurulamadı\" / \"Chromium indirilemedi\" diyor", "İnternet ya da kurum proxy'si engelliyor.", "Bağlantıyı ve proxy ayarlarını kontrol edip KURULUM.bat'ı tekrar çalıştırın. Kurum ağında `HTTPS_PROXY` ortam değişkeni gerekebilir."],
  ["Arayüz açılmıyor, \"tkinter\" hatası", "Python Tkinter'sız kurulmuş (Linux'ta sık).", "Linux: `sudo apt install python3-tk`; Windows: Python'u python.org kurulumuyla yeniden kurun. Komut satırı Tkinter'sız da çalışır."],
  ["Ana sayfada \"Kurulum eksik\" uyarısı", "Paket ya da Chromium eksik.", "Uyarıdaki **Bağımlılıkları kur** düğmesi; ardından **Ortam kontrolü**."],
  ["Arayüz yavaş, sayfa geçişlerinde ya da pencere boyutlanırken kasıyor", "Modern görünüm (sv-ttk) her öğeyi resimle çizer; bazı Windows bilgisayarlarda, özellikle yüksek ekran ölçeklemesinde ağır kalır.", "**Ayarlar → Genel → Arayüz görünümü**: `hizli` seçip kaydedin ve programı yeniden açın. Renkler ve düzen aynı kalır, çizim yaklaşık iki kat hızlanır."],
  ["Testte çok sayıda ERROR / zaman aşımı", "Sunucu yavaş ya da eşzamanlılık yüksek; VPN kopmuş.", "Eşzamanlılığı 2–3'e, zaman aşımını 45–60 sn'ye ayarlayın; **Hatalı sayfaları yeniden test et**. VPN'i kontrol edin."],
  ["Bütün sayfalar FAIL, durum boş", "Siteye ulaşılamıyor (adres yanlış, VPN yok).", "Site adresini tarayıcıda açmayı deneyin; profilin başlangıç adresini kontrol edin."],
  ["Keşif bitmiyor, sayfa sayısı çok büyük", "Filtre/takvim gibi sonsuz kombinasyonlu adresler.", "Hariç desenler, silinecek parametreler ve sorgu sınırını ayarlayın; `kesif/` klasörünü silip yeniden başlatın."],
  ["Keşif çok az sayfa buldu", "Linkler JavaScript ile üretiliyor (SPA).", "**Tarayıcıyla keşfet**'i açın."],
  ["Yapay zekâ: \"model bu hesapta kullanılamıyor (404)\"", "Model adı yanlış ya da hesapta yok.", "**Yapay zekâ sağlayıcılarını dene** ile kullanılabilir modelleri görün, ayarı düzeltin."],
  ["Yapay zekâ: \"günlük kota doldu\"", "Ücretsiz katman kotası.", "Ertesi gün aynı adımı çalıştırın; kaldığı yerden devam eder."],
  ["Yapay zekâ adımı \"ornekler.csv yok\" diyor", "Önceki adımlar çalışmamış.", "Yapay zekâ hattını baştan (1. adımdan) çalıştırın."],
  ["Canlı doğrulama \"results.jsonl yok\" diyor", "Doğrulama çekimi yapılmamış ya da yarıda kalmış.", "7. adımı yeniden çalıştırın."],
  ["\"Etiketleri işle\" CSV'yi okuyamıyor", "Dosya başka yerde ya da sayfadan indirilmemiş.", "Etiketleme sayfasındaki **CSV indir**'i kullanın; dosya İndirilenler'de değilse Ayarlar'da yolunu verin."],
  ["Bologna: \"docker\" bulunamadı", "Docker Desktop kurulu değil ya da çalışmıyor.", "Docker Desktop'ı kurup başlatın; ya da Ayarlar'da Bologna modunu \"yerel\" yapıp Go + PostgreSQL kurun."],
  ["Disk doldu", "Ekran görüntüleri.", "Eski profillerin `ciktilar/<profil>/test_output/screenshots/` klasörlerini arşivleyip silin."],
], [1.6, 1.5, 2.6]);
P("Çözemediğiniz bir sorunda **Hatalar ve uyarılar > Panoya kopyala** ile listeyi ve ilgili adımın `merkez_kayitlari/` altındaki kayıt dosyasını paylaşın. Ayarlar > Genel > **Ayrıntılı kayıt** açıkken kayıt, her komutun klasörünü ve argümanlarını da içerir.");

// ---- 13. SSS
H1("13. Sık sorulan sorular");
const sss = [
  ["Program siteyi değiştirir mi?", "Hayır. Sayfalar yalnızca okunur. CSS denemeleri yalnızca programın açtığı tarayıcı sekmesine eklenir; site dosyalarına dokunulmaz."],
  ["Sunucuyu zorlar mı?", "Eşzamanlı sekme sayısı ve saniyede istek ayarlarıyla sınırlanır. Ön-prodüksiyon sunucularında 4 eşzamanlı sekme önerilir; 10 gibi yüksek değerler zaman aşımlarına yol açabilir."],
  ["Yarıda kalan işi baştan mı çalıştırmam gerekir?", "Hayır. Aynı adımı yeniden çalıştırın; test, keşif, yapay zekâ analizi ve Bologna kaldığı yerden devam eder."],
  ["Yapay zekâ olmadan kullanılabilir mi?", "Evet. Test, belge, link, görsel denetim, doğrulama, canlı doğrulama, otomatik taşma düzeltme ve teslim yapay zekâ gerektirmez."],
  ["Bulgulara ne kadar güvenebilirim?", "Kodla ölçülen bulgular (HTTP durumu, taşma, kırık link) kesindir. Yapay zekâ bulguları iki modelle ve canlı doğrulamayla süzülür; yine de elle etiketlemeyle bir örneklem kontrol edilmelidir. İsabet tabloları (7.5, 7.7) bunun ölçüsünü verir."],
  ["Bir sonucu bir başkasına nasıl iletirim?", "**Teslim > Teslim paketini oluştur** ve `TESLIM/` klasörünü paylaşın; `index.html` her dosyanın ne olduğunu açıklar."],
  ["Başka bir bilgisayarda kaldığım yerden devam edebilir miyim?", "Evet: program klasörünü (`ciktilar/` dahil) kopyalayın ve orada BASLAT.bat'ı çalıştırın; `.venv` yeniden kurulur."],
];
sss.forEach(([s, c]) => { P(`**${s}**`, { spacing: { after: 40 }, keepNext: true }); P(c); });

// ---- Ek A
H1("Ek A. Bologna");
P("Bologna adımları, OİBS kullanan bir üniversitenin **Bologna Bilgi Paketi**'ni tarayıp birimler, programlar, program çıktıları, ders planları ve ders detaylarını (öğrenme çıktısı × program çıktısı katkı matrisi dahil) ilişkileri koruyarak PostgreSQL'e yazar.");
sirali([
  "Docker Desktop'ı kurup başlatın (ya da Ayarlar'da modu \"yerel\" yapıp Go ve PostgreSQL kurun, PostgreSQL adresini girin).",
  "**Bologna > PostgreSQL'i başlat (Docker)**.",
  "Deneme için **Tek program tara** (varsayılan 1371: Bilgisayar Mühendisliği, ~1 dk).",
  "Tamamı için **Tüm siteyi tara** (~3,5 saat). Yarıda kalırsa **Kesilen taramayı sürdür**.",
  "**Veritabanı istatistikleri** ile tablo kayıt sayılarını görün. Veritabanı adresi: `postgres://bologna:bologna@localhost:5432/bologna` (DBeaver, pgAdmin ile bağlanılabilir).",
]);
P("Başka bir üniversite için profilde **OİBS Bologna adresi**'ni değiştirin. Veri modeli, örnek SQL sorguları ve ayrıntılar: `bologna-scraper/README.md`.");

// ---- Ek B
H1("Ek B. Geliştirme notları");
madde([
  "Yeni bir araç programa `merkez/adimlar.py`'deki listeye bir adım eklenerek bağlanır; arayüz, komut satırı, durum ve kayıtlar yeni adımı kendiliğinden kullanır.",
  "Testler: `python -m unittest discover -s tests -v` ve `cd bologna-scraper && go test ./...`. GitHub Actions bunları Windows ve Linux'ta, Python 3.9 ve 3.12 ile çalıştırır.",
  "**Sözleşme testleri**, programın araçlara gönderdiği her seçeneğin aracın kodunda tanımlı olduğunu denetler; araçlar güncellendiğinde uyumsuzluğu yakalar.",
  "Görsel denetim `gorsel-denetim` reposunda geliştirilir; `tools/visual_audit/` ve `tools/tester_v3_evidence.py` oradaki `denetim/` ve `cekim/tester.py` ile aynı araçlardır ve üç yönlü birleştirmeyle güncellenir.",
]);

// ------------------------------------------------------------------ kapak ve içindekiler
const kapak = [
  new Paragraph({ children: [], spacing: { before: 2400 } }),
  new Paragraph({ alignment: AlignmentType.LEFT, spacing: { line: 240, lineRule: LineRuleType.AUTO, after: 240 }, children: [new TextRun({ text: "Web Denetim Merkezi", bold: true, size: 64, color: MAVI })] }),
  new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 400 }, children: [new TextRun({ text: "Kullanım Kılavuzu", size: 40, color: "404040" })] }),
  new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: MAVI, space: 4 } }, children: [] }),
  new Paragraph({ spacing: { before: 300, after: 120 }, children: parcala("Web sitelerini baştan sona test eden ve denetleyen masaüstü programı: site keşfi, kanıtlı tarayıcı testi, belge/link/görsel denetim, yapay zekâ destekli görsel denetim, bulguların canlı doğrulanması, otomatik taşma düzeltme önerisi ve OİBS Bologna aktarımı.", { size: 24, color: "404040" }) }),
  new Paragraph({ spacing: { before: 600 }, children: [new TextRun({ text: "Sürüm 1.0  ·  Ekim 2026", size: 22, color: "595959" })] }),
  new Paragraph({ children: [new TextRun({ text: "github.com/mehmetfatihvar/web-denetim-merkezi", size: 22, color: "595959" })] }),
  new Paragraph({ children: [new TextRun({ text: "Mersin Üniversitesi staj çalışması", size: 22, color: "595959" })] }),
];
function icindekiler() {
  const satirlar = [new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun("İçindekiler")] })];
  for (const [seviye, metin, ad] of basliklar) {
    if (seviye > 2) continue;
    const sayfa = SAYFALAR[metin] !== undefined ? String(SAYFALAR[metin]) : "00";
    satirlar.push(new Paragraph({
      indent: { left: seviye === 1 ? 0 : 400 }, spacing: { before: seviye === 1 ? 120 : 0, after: 40 },
      tabStops: [{ type: TabStopType.RIGHT, position: GENISLIK, leader: LeaderType.DOT }],
      children: [new InternalHyperlink({ anchor: ad, children: [
        new TextRun({ text: metin, bold: seviye === 1, size: seviye === 1 ? 22 : 20 }),
        new TextRun({ children: [new Tab(), sayfa], size: 20, bold: seviye === 1 }),
      ] })],
    }));
  }
  return satirlar;
}

const doc = new Document({
  creator: "Web Denetim Merkezi", title: "Web Denetim Merkezi — Kullanım Kılavuzu", language: "tr-TR",
  styles: {
    default: { document: { run: { font: YAZI, size: 21 }, paragraph: { spacing: { line: 276, lineRule: LineRuleType.AUTO } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, font: YAZI, color: MAVI }, paragraph: { spacing: { before: 120, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, font: YAZI, color: MAVI }, paragraph: { spacing: { before: 300, after: 140 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: YAZI, color: "2F2F2F" }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "madde", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
    ...numaraTanimlari,
  ] },
  sections: [
    { properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } }, children: kapak },
    { properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 }, pageNumbers: { start: 2 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "Web Denetim Merkezi — Kullanım Kılavuzu", size: 16, color: "808080" })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Sayfa ", PageNumber.CURRENT], size: 16, color: "808080" })] })] }) },
      children: [...icindekiler(), ...icerik] },
  ],
});

// docx kütüphanesi bütün yer imlerine aynı w:id'yi veriyor: sırayla yeniden numarala
async function yerimleriniDuzelt(b) {
  const JSZip = require(require.resolve("jszip", { paths: [path.dirname(require.resolve("docx"))] }));
  const zip = await JSZip.loadAsync(b);
  let xml = await zip.file("word/document.xml").async("string");
  let n = 0;
  xml = xml.replace(/<w:bookmark(Start|End)\b([^>]*?)w:id="\d+"/g, (m, tur, ara) => {
    if (tur === "Start") n += 1;
    return `<w:bookmark${tur}${ara}w:id="${n}"`;
  });
  zip.file("word/document.xml", xml);
  return zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

Packer.toBuffer(doc).then(yerimleriniDuzelt).then((b) => {
  fs.writeFileSync(CIKTI, b);
  fs.writeFileSync(path.join(KOK, "basliklar.json"), JSON.stringify(basliklar.filter((b) => b[0] <= 2).map((b) => b[1]), null, 1));
  console.log("yazıldı:", CIKTI, "şekil:", sekilNo, "başlık:", basliklar.length);
});
