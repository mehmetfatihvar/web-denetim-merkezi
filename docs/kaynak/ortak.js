// Word belgeleri için ortak yardımcılar (teknik.js kullanır): başlık, paragraf, madde, tablo,
// kutu, kod, görsel, içindekiler ve yazdırma. Satır içi biçim: **kalın**, `kod`.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, HeadingLevel, LevelFormat, Header, Footer, PageNumber,
  BorderStyle, Bookmark, InternalHyperlink, TableLayoutType, Tab, TabStopType, LeaderType, LineRuleType,
} = require("docx");

const YAZI = "Arial", KOD = "Courier New";
const MAVI = "1F4E79", ACIK = "EAF1F8", GRI = "F2F2F2", KENAR = "BFBFBF";
const GENISLIK = 9638;                    // A4, 2 cm kenar boşlukları (DXA)

function belge(KOK) {
  const icerik = [];
  const basliklar = [];
  const numaraTanimlari = [];
  let yerimiNo = 0, numaraNo = 0, sekilNo = 0;

  function parcala(metin, temel = {}) {
    const runs = [];
    const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let son = 0, m;
    while ((m = re.exec(metin))) {
      if (m.index > son) runs.push(new TextRun({ text: metin.slice(son, m.index), ...temel }));
      const p = m[0];
      if (p.startsWith("**")) runs.push(new TextRun({ text: p.slice(2, -2), bold: true, ...temel }));
      else runs.push(new TextRun({ text: p.slice(1, -1), font: KOD, size: 18, ...temel }));
      son = m.index + p.length;
    }
    if (son < metin.length) runs.push(new TextRun({ text: metin.slice(son), ...temel }));
    return runs;
  }

  function baslik(seviye, metin, yeniSayfa = false) {
    const ad = `b${++yerimiNo}`;
    basliklar.push([seviye, metin, ad]);
    icerik.push(new Paragraph({
      heading: [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][seviye - 1],
      pageBreakBefore: yeniSayfa,
      children: [new Bookmark({ id: ad, children: [new TextRun(metin)] })],
    }));
  }
  const P = (m, ek = {}) => icerik.push(new Paragraph({ children: parcala(m), spacing: { after: 120 }, ...ek }));
  const madde = (liste, ref = "madde") => liste.forEach((m) =>
    icerik.push(new Paragraph({ numbering: { reference: ref, level: 0 }, children: parcala(m), spacing: { after: 60 } })));
  const sirali = (liste) => {
    const ref = `sira${++numaraNo}`;
    numaraTanimlari.push({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
      alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });
    madde(liste, ref);
  };

  function kutu(baslikMetni, satirlar, renk = ACIK, kenar = MAVI) {
    const cocuklar = [];
    if (baslikMetni) cocuklar.push(new Paragraph({ children: [new TextRun({ text: baslikMetni, bold: true, color: kenar })], spacing: { after: 60 } }));
    satirlar.forEach((s) => cocuklar.push(new Paragraph({ children: parcala(s), spacing: { after: 60 } })));
    const yok = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
    icerik.push(new Table({
      width: { size: GENISLIK, type: WidthType.DXA }, columnWidths: [GENISLIK], layout: TableLayoutType.FIXED,
      rows: [new TableRow({ cantSplit: true, children: [new TableCell({
        width: { size: GENISLIK, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: renk, color: "auto" },
        margins: { top: 100, bottom: 100, left: 160, right: 160 },
        borders: { left: { style: BorderStyle.SINGLE, size: 24, color: kenar }, top: yok, bottom: yok, right: yok },
        children: cocuklar })] })],
    }));
    icerik.push(new Paragraph({ children: [], spacing: { after: 60 } }));
  }

  function kod(satirlar) {
    const k = { style: BorderStyle.SINGLE, size: 4, color: KENAR };
    icerik.push(new Table({
      width: { size: GENISLIK, type: WidthType.DXA }, columnWidths: [GENISLIK], layout: TableLayoutType.FIXED,
      rows: [new TableRow({ cantSplit: true, children: [new TableCell({
        width: { size: GENISLIK, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: GRI, color: "auto" },
        margins: { top: 80, bottom: 80, left: 140, right: 140 },
        borders: { top: k, bottom: k, left: k, right: k },
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
        children: bas ? [new TextRun({ text: s, bold: true, color: "FFFFFF", size: 18 })] : parcala(s, { size: 18 }),
        spacing: { after: 20 } })),
    });
    icerik.push(new Table({
      width: { size: GENISLIK, type: WidthType.DXA }, columnWidths: gen, layout: TableLayoutType.FIXED,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: basliklar_.map((b, i) => hucre(b, i, true)) }),
             ...satirlar.map((r) => new TableRow({ cantSplit: true, children: r.map((h, i) => hucre(h, i, false)) }))],
    }));
    icerik.push(new Paragraph({ children: [], spacing: { after: 100 } }));
  }

  function gorsel(dosya, aciklama, genislikPx = 640) {
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

  function icindekiler(SAYFALAR) {
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

  function kapakSayfasi(ust, alt, aciklama, bilgiler) {
    return [
      new Paragraph({ children: [], spacing: { before: 2400 } }),
      new Paragraph({ spacing: { line: 240, lineRule: LineRuleType.AUTO, after: 240 }, children: [new TextRun({ text: ust, bold: true, size: 64, color: MAVI })] }),
      new Paragraph({ spacing: { after: 400 }, children: [new TextRun({ text: alt, size: 40, color: "404040" })] }),
      new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: MAVI, space: 4 } }, children: [] }),
      new Paragraph({ spacing: { before: 300, after: 120 }, children: parcala(aciklama, { size: 24, color: "404040" }) }),
      ...bilgiler.map((b, i) => new Paragraph({ spacing: { before: i === 0 ? 600 : 0 }, children: [new TextRun({ text: b, size: 22, color: "595959" })] })),
    ];
  }

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

  function yaz(CIKTI, SAYFALAR, baslikMetni, kapak) {
    const kenarlar = { top: 1134, bottom: 1134, left: 1134, right: 1134 };
    const doc = new Document({
      creator: "Web Denetim Merkezi", title: baslikMetni, language: "tr-TR",
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
        { properties: { page: { margin: kenarlar } }, children: kapak },
        { properties: { page: { margin: kenarlar, pageNumbers: { start: 2 } } },
          headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: baslikMetni, size: 16, color: "808080" })] })] }) },
          footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
            children: [new TextRun({ children: ["Sayfa ", PageNumber.CURRENT], size: 16, color: "808080" })] })] }) },
          children: [...icindekiler(SAYFALAR), ...icerik] },
      ],
    });
    return Packer.toBuffer(doc).then(yerimleriniDuzelt).then((b) => {
      fs.writeFileSync(CIKTI, b);
      fs.writeFileSync(path.join(KOK, "basliklar.json"), JSON.stringify(basliklar.filter((x) => x[0] <= 2).map((x) => x[1]), null, 1));
      console.log("yazıldı:", CIKTI, "şekil:", sekilNo, "başlık:", basliklar.length);
    });
  }

  return {
    H1: (m) => baslik(1, m, true), H2: (m) => baslik(2, m), H3: (m) => baslik(3, m),
    P, madde, sirali, tablo, kod, gorsel, kapakSayfasi, yaz,
    not: (s) => kutu("Not", Array.isArray(s) ? s : [s]),
    ipucu: (s) => kutu("İpucu", Array.isArray(s) ? s : [s], "EAF6EC", "2E7D32"),
    dikkat: (s) => kutu("Dikkat", Array.isArray(s) ? s : [s], "FDF3E1", "B26A00"),
    ozet: (b, s) => kutu(b, Array.isArray(s) ? s : [s]),
  };
}

module.exports = { belge };
