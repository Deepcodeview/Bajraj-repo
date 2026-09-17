import PDFDocument from "pdfkit";

const BLUE       = "#1a56db";
const LIGHT_BLUE = "#eff6ff";
const BLUE_BD    = "#bfdbfe";
const GREEN      = "#059669";
const GREEN_BG   = "#f0fdf4";
const GREEN_BD   = "#bbf7d0";
const RED        = "#dc2626";
const RED_BG     = "#fef2f2";
const RED_BD     = "#fecaca";
const AMBER      = "#d97706";
const AMBER_BG   = "#fffbeb";
const AMBER_BD   = "#fde68a";
const PURPLE     = "#7c3aed";
const PURPLE_BG  = "#f5f3ff";
const PURPLE_BD  = "#ddd6fe";
const GRAY       = "#6b7280";
const DARK       = "#111827";
const ROW_ALT    = "#f9fafb";
const WHITE      = "#ffffff";
const BORDER     = "#e5e7eb";
const HEADER_BG  = "#1e40af";

export function generateEmployeeReportPdf(report) {
  return new Promise((resolve, reject) => {
    const doc     = new PDFDocument({ margin: 45, size: "A4" });
    const buffers = [];
    doc.on("data",  c => buffers.push(c));
    doc.on("end",   () => resolve(Buffer.concat(buffers)));
    doc.on("error", reject);

    const PW = doc.page.width;
    const W  = PW - 90;
    const L  = 45;

    // ── Watermark ─────────────────────────────────────────────────────────────
    doc.save();
    doc.rotate(-45, { origin: [PW / 2, doc.page.height / 2] });
    doc.fontSize(52).fillColor("#d1d5db").fillOpacity(0.15).font("Helvetica-Bold")
       .text(report.organization.name, 0, doc.page.height / 2 - 26, { align: "center", width: PW });
    doc.restore();
    doc.fillOpacity(1);

    // ── Top accent bar ────────────────────────────────────────────────────────
    doc.rect(L, 38, W, 4).fill(BLUE);

    // ── Header box ───────────────────────────────────────────────────────────
    doc.rect(L, 42, W, 72).fill(LIGHT_BLUE);
    doc.rect(L, 42, W, 72).lineWidth(1).stroke(BLUE_BD);
    doc.rect(L, 42, 4, 72).fill(BLUE);

    doc.fontSize(16).fillColor(BLUE).font("Helvetica-Bold")
       .text(report.organization.name, L + 16, 53, { width: W - 32 });
    doc.fontSize(9).fillColor(GRAY).font("Helvetica")
       .text("Employee Performance Report", L + 16, 74);

    const dateLabel = report.dateRange.start.slice(0, 10) === report.dateRange.end.slice(0, 10)
      ? report.dateRange.start.slice(0, 10)
      : `${report.dateRange.start.slice(0, 10)}  to  ${report.dateRange.end.slice(0, 10)}`;
    doc.fontSize(9).fillColor(DARK).font("Helvetica-Bold")
       .text(`Date: ${dateLabel}`, L + 16, 74, { align: "right", width: W - 32 });

    const storeNames = report.stores.map(s => s.name).join("  |  ");
    doc.fontSize(8.5).fillColor(BLUE).font("Helvetica")
       .text(`Store: ${storeNames}`, L + 16, 90, { width: W - 32 });
    doc.fontSize(8).fillColor(GRAY).font("Helvetica")
       .text(`Generated: ${new Date().toLocaleString("en-IN")}`, L + 16, 90, { align: "right", width: W - 32 });

    // ── Summary Cards ─────────────────────────────────────────────────────────
    const cardY = 128;
    const cardH = 62;
    const gap   = 10;
    const cardW = (W - gap * 3) / 4;

    const cards = [
      { label: "Total Employees",    value: report.totalEmployees, color: BLUE,   bg: LIGHT_BLUE, bd: BLUE_BD   },
      { label: "Present Today",      value: report.totalPresent,   color: GREEN,  bg: GREEN_BG,   bd: GREEN_BD  },
      { label: "Customers Served",   value: report.totalCustomers, color: AMBER,  bg: AMBER_BG,   bd: AMBER_BD  },
      { label: "Avg Response (sec)", value: report.avgResponseSec, color: PURPLE, bg: PURPLE_BG,  bd: PURPLE_BD },
    ];

    cards.forEach((card, i) => {
      const x = L + i * (cardW + gap);
      doc.rect(x, cardY, cardW, cardH).fill(card.bg);
      doc.rect(x, cardY, cardW, cardH).lineWidth(1).stroke(card.bd);
      doc.rect(x, cardY, cardW, 3).fill(card.color);
      doc.fontSize(28).fillColor(card.color).font("Helvetica-Bold")
         .text(String(card.value), x + 10, cardY + 12, { width: cardW - 20 });
      doc.fontSize(8).fillColor(GRAY).font("Helvetica")
         .text(card.label, x + 10, cardY + 44, { width: cardW - 20 });
    });

    // ── Section heading ───────────────────────────────────────────────────────
    const secY = cardY + cardH + 18;
    doc.fontSize(10).fillColor(DARK).font("Helvetica-Bold")
       .text("Employee Performance Records", L, secY);
    doc.rect(L, secY + 15, W, 1).fill(BORDER);

    // ── Table ─────────────────────────────────────────────────────────────────
    const tableTop = secY + 22;
    const rowH     = 22;

    const cols = [
      { label: "#",               w: 24,  align: "center" },
      { label: "Employee",        w: 120, align: "left"   },
      { label: "Code",            w: 60,  align: "center" },
      { label: "Hours Worked",    w: 72,  align: "center" },
      { label: "Customers",       w: 65,  align: "center" },
      { label: "Avg Response",    w: 72,  align: "center" },
      { label: "Sessions",        w: 55,  align: "center" },
      { label: "Status",          w: 62,  align: "center" },
    ];

    const drawTableHeader = (y) => {
      doc.rect(L, y, W, rowH).fill(HEADER_BG);
      let cx = L;
      cols.forEach((col, ci) => {
        if (ci > 0) doc.moveTo(cx, y).lineTo(cx, y + rowH).strokeColor("#3b82f6").lineWidth(0.5).stroke();
        doc.fontSize(8.5).fillColor(WHITE).font("Helvetica-Bold")
           .text(col.label, cx + 4, y + 7, { width: col.w - 8, align: col.align });
        cx += col.w;
      });
      doc.rect(L, y, W, rowH).lineWidth(1).stroke("#1e3a8a");
    };

    drawTableHeader(tableTop);
    let rowY = tableTop + rowH;

    if (report.records.length === 0) {
      doc.rect(L, rowY, W, 30).fill(ROW_ALT);
      doc.rect(L, rowY, W, 30).lineWidth(0.5).stroke(BORDER);
      doc.fontSize(9).fillColor(GRAY).font("Helvetica")
         .text("No employee records found for this date.", L, rowY + 10, { width: W, align: "center" });
      rowY += 30;
    }

    report.records.forEach((rec, idx) => {
      if (rowY + rowH > doc.page.height - 55) {
        _addFooter(doc, L, W, report.organization.name);
        doc.addPage();
        doc.save();
        doc.rotate(-45, { origin: [doc.page.width / 2, doc.page.height / 2] });
        doc.fontSize(52).fillColor("#d1d5db").fillOpacity(0.15).font("Helvetica-Bold")
           .text(report.organization.name, 0, doc.page.height / 2 - 26, { align: "center", width: doc.page.width });
        doc.restore();
        doc.fillOpacity(1);
        rowY = 45;
        drawTableHeader(rowY);
        rowY += rowH;
      }

      const bg = idx % 2 === 0 ? WHITE : ROW_ALT;
      doc.rect(L, rowY, W, rowH).fill(bg);
      doc.rect(L, rowY, W, rowH).lineWidth(0.5).stroke(BORDER);

      const statusColor = rec.status === "Absent" ? RED : rec.status === "Present" ? GREEN : AMBER;

      const rowData = [
        String(idx + 1),
        rec.name,
        rec.employeeCode,
        rec.hoursWorked,
        String(rec.customersServed),
        rec.avgResponseSec,
        String(rec.sessions),
        rec.status,
      ];

      let cx = L;
      cols.forEach((col, ci) => {
        if (ci > 0) doc.moveTo(cx, rowY).lineTo(cx, rowY + rowH).strokeColor(BORDER).lineWidth(0.5).stroke();
        const isStatus = ci === 7;
        const color    = isStatus ? statusColor : ci === 0 ? GRAY : DARK;
        const font     = isStatus ? "Helvetica-Bold" : "Helvetica";
        doc.fontSize(8).fillColor(color).font(font)
           .text(rowData[ci], cx + 4, rowY + 7, { width: col.w - 8, align: col.align, ellipsis: true });
        cx += col.w;
      });

      rowY += rowH;
    });

    doc.moveTo(L, rowY).lineTo(L + W, rowY).strokeColor(BORDER).lineWidth(1).stroke();

    if (rowY + 20 < doc.page.height - 55) {
      doc.rect(L, rowY, W, 20).fill(LIGHT_BLUE);
      doc.rect(L, rowY, W, 20).lineWidth(0.5).stroke(BLUE_BD);
      doc.fontSize(8).fillColor(BLUE).font("Helvetica-Bold")
         .text(
           `Total: ${report.totalEmployees}  |  Present: ${report.totalPresent}  |  Customers Served: ${report.totalCustomers}  |  Avg Response: ${report.avgResponseSec}s`,
           L + 8, rowY + 6, { width: W - 16 }
         );
    }

    _addFooter(doc, L, W, report.organization.name);
    doc.end();
  });
}

function _addFooter(doc, L, W, orgName) {
  const fY = doc.page.height - 36;
  doc.rect(L, fY - 6, W, 1).fill(BORDER);
  doc.fontSize(7.5).fillColor("#9ca3af").font("Helvetica")
     .text(`${orgName}  •  Confidential  •  ${new Date().toLocaleString("en-IN")}`, L, fY, { align: "center", width: W });
}
