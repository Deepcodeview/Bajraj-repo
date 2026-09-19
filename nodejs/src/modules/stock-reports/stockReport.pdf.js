import PDFDocument from "pdfkit";
import fs from "fs";

const NAVY      = "#0b2e4f";
const BLUE      = "#1565c0";
const RED       = "#dc2626";
const ORANGE    = "#d97706";
const GREEN     = "#16a34a";
const GRAY      = "#6b7280";
const DARK      = "#101828";
const BORDER    = "#e3e8ef";
const ROW_ALT   = "#f7fafc";
const WHITE     = "#ffffff";
const HEADER_BG = "#0d3f6e";
const RED_BG    = "#fef2f2";
const ORG_BG    = "#fff7ed";

const money = (n) => `${Math.round((n || 0) * 100)}%`;

function fmtDate(d) {
  return new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
}

function fmtTime(d) {
  return new Date(d).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true, timeZone: "Asia/Kolkata" });
}

function statusColor(status) {
  if (status === "EMPTY")     return RED;
  if (status === "LOW STOCK") return ORANGE;
  return GREEN;
}

function statusBg(status) {
  if (status === "EMPTY")     return "#fef2f2";
  if (status === "LOW STOCK") return "#fffbeb";
  return "#f0fdf4";
}

function panel(doc, x, y, w, h, bg = WHITE) {
  doc.rect(x, y, w, h).fill(bg);
  doc.rect(x, y, w, h).lineWidth(1).stroke(BORDER);
}

function sectionHeading(doc, x, y, w, title) {
  doc.rect(x, y, 3, 12).fill(BLUE);
  doc.fontSize(10.5).fillColor(NAVY).font("Helvetica-Bold").text(title, x + 9, y);
  doc.moveTo(x, y + 17).lineTo(x + w, y + 17).strokeColor(BORDER).lineWidth(1).stroke();
}

export function generateStockReportPdf(data) {
  return new Promise((resolve, reject) => {
    const { organization, summary, reports, dateRange } = data;

    const doc     = new PDFDocument({ margin: 36, size: "A4" });
    const buffers = [];
    doc.on("data",  c => buffers.push(c));
    doc.on("end",   () => resolve(Buffer.concat(buffers)));
    doc.on("error", reject);

    const L  = 36;
    const PW = doc.page.width;
    const W  = PW - L * 2;

    // ── Header ──────────────────────────────────────────────────────────────
    doc.rect(L, 30, W, 3).fill(RED);
    doc.rect(L, 33, W, 76).fill(NAVY);

    doc.fontSize(17).fillColor(WHITE).font("Helvetica-Bold")
       .text((organization?.name || "Store").toUpperCase(), L + 14, 48, { width: W * 0.5 });
    doc.fontSize(8).fillColor("#f9a8a8").font("Helvetica")
       .text("STOCK MISSING REPORT", L + 14, 70, { width: W * 0.5 });

    // Meta — right side
    const metaX = L + W - 220;
    const meta  = [
      ["Report Period", dateRange || "Today"],
      ["Camera",        "CAM-3 (Shelf Monitor)"],
      ["Generated",     new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })],
    ];
    let my = 39;
    meta.forEach(([k, v]) => {
      doc.fontSize(6.5).fillColor("#f9a8a8").font("Helvetica-Bold").text(k, metaX, my, { width: 220 });
      doc.fontSize(7.4).fillColor(WHITE).font("Helvetica").text(v, metaX, my + 7.5, { width: 220, ellipsis: true });
      my += 17;
    });

    // ── Summary Cards ────────────────────────────────────────────────────────
    const cardY = 123;
    const cardH = 58;
    const gap   = 8;
    const cardW = (W - gap * 3) / 4;

    const cards = [
      { label: "Total Detected",  value: String(summary.total),         color: BLUE,   dot: "#1565c0" },
      { label: "Today's Alerts",  value: String(summary.todayCount),    color: ORANGE, dot: "#d97706" },
      { label: "Empty Shelf",     value: String(summary.emptyCount),    color: RED,    dot: "#dc2626" },
      { label: "Low Stock",       value: String(summary.lowStockCount), color: ORANGE, dot: "#d97706" },
    ];

    cards.forEach((c, i) => {
      const x = L + i * (cardW + gap);
      panel(doc, x, cardY, cardW, cardH);
      doc.rect(x, cardY, cardW, 3).fill(c.color);
      doc.fontSize(7.3).fillColor(GRAY).font("Helvetica").text(c.label, x + 8, cardY + 10, { width: cardW - 16 });
      doc.fontSize(22).fillColor(c.color).font("Helvetica-Bold").text(c.value, x + 8, cardY + 20, { width: cardW - 16 });
    });

    // ── Last Detected Banner ─────────────────────────────────────────────────
    if (summary.lastDetected) {
      const banY = cardY + cardH + 10;
      doc.rect(L, banY, W, 28).fill(RED_BG);
      doc.rect(L, banY, W, 28).lineWidth(1).stroke("#fca5a5");
      doc.rect(L, banY, 3, 28).fill(RED);
      doc.fontSize(8).fillColor(RED).font("Helvetica-Bold")
         .text("⚠  Last Detection:", L + 10, banY + 8);
      doc.fontSize(8).fillColor(DARK).font("Helvetica")
         .text(
           `Camera: ${summary.lastDetected.cameraId}   Status: ${summary.lastDetected.status}   Time: ${fmtTime(summary.lastDetected.detectedAt)}`,
           L + 110, banY + 8, { width: W - 120 }
         );
    }

    // ── Report Table ─────────────────────────────────────────────────────────
    const tableY = cardY + cardH + 48;
    sectionHeading(doc, L, tableY, W, "Stock Missing Events");

    const cols = [
      { label: "#",           w: 22,         align: "center" },
      { label: "Camera",      w: 55,         align: "center" },
      { label: "Status",      w: 72,         align: "center" },
      { label: "Occupancy",   w: 62,         align: "center" },
      { label: "OOS Count",   w: 58,         align: "center" },
      { label: "Empty Zones", w: 62,         align: "center" },
      { label: "Date",        w: 72,         align: "center" },
      { label: "Time",        w: 72,         align: "center" },
      { label: "Detected Items", w: W - 22 - 55 - 72 - 62 - 58 - 62 - 72 - 72, align: "left" },
    ];

    const rowH   = 20;
    let   rowY   = tableY + 24;

    // Header row
    doc.rect(L, rowY, W, rowH).fill(HEADER_BG);
    let cx = L;
    cols.forEach(col => {
      doc.fontSize(7).fillColor(WHITE).font("Helvetica-Bold")
         .text(col.label, cx + 3, rowY + 6, { width: col.w - 6, align: col.align, height: 10, ellipsis: true });
      cx += col.w;
    });
    rowY += rowH;

    if (!reports || reports.length === 0) {
      doc.rect(L, rowY, W, 32).fill(ROW_ALT);
      doc.fontSize(9).fillColor(GRAY).font("Helvetica")
         .text("No stock missing events recorded for this period.", L, rowY + 10, { width: W, align: "center" });
      rowY += 32;
    }

    (reports || []).forEach((r, idx) => {
      // New page if needed
      if (rowY + rowH > doc.page.height - 50) {
        _footer(doc, L, W);
        doc.addPage();
        rowY = 45;
        doc.rect(L, rowY, W, rowH).fill(HEADER_BG);
        let cx2 = L;
        cols.forEach(col => {
          doc.fontSize(7).fillColor(WHITE).font("Helvetica-Bold")
             .text(col.label, cx2 + 3, rowY + 6, { width: col.w - 6, align: col.align, height: 10, ellipsis: true });
          cx2 += col.w;
        });
        rowY += rowH;
      }

      const bg = idx % 2 === 0 ? WHITE : ROW_ALT;
      doc.rect(L, rowY, W, rowH).fill(bg);
      doc.rect(L, rowY, W, rowH).lineWidth(0.5).stroke(BORDER);

      const sc    = statusColor(r.status);
      const items = Object.entries(r.labelCounts || {})
        .map(([k, v]) => `${k}:${v}`).join(", ") || "--";

      const vals = [
        String(idx + 1),
        r.cameraId || "--",
        r.status   || "--",
        `${Math.round((r.occupancy || 0) * 100)}%`,
        String(r.outOfStock  || 0),
        String(r.emptyZones  || 0),
        r.date     || "--",
        r.time     || "--",
        items,
      ];

      let cx3 = L;
      cols.forEach((col, ci) => {
        const isStatus = ci === 2;
        const color    = isStatus ? sc : ci === 0 ? GRAY : DARK;
        const font     = isStatus || ci === 8 ? "Helvetica-Bold" : "Helvetica";
        doc.fontSize(7).fillColor(color).font(font)
           .text(vals[ci], cx3 + 3, rowY + 6,
             { width: col.w - 6, align: col.align, height: 10, ellipsis: true });
        cx3 += col.w;
      });

      rowY += rowH;
    });

    // ── Screenshot section ───────────────────────────────────────────────────
    const withScreenshots = (reports || []).filter(r => r.screenshotPath && fs.existsSync(r.screenshotPath)).slice(0, 6);
    if (withScreenshots.length > 0) {
      if (rowY + 180 > doc.page.height - 50) {
        _footer(doc, L, W);
        doc.addPage();
        rowY = 45;
      } else {
        rowY += 16;
      }

      sectionHeading(doc, L, rowY, W, "Detection Screenshots");
      rowY += 24;

      const imgW = (W - 16) / 3;
      const imgH = 100;
      withScreenshots.forEach((r, i) => {
        const col = i % 3;
        const row = Math.floor(i / 3);
        const ix  = L + col * (imgW + 8);
        const iy  = rowY + row * (imgH + 28);

        if (iy + imgH + 28 > doc.page.height - 50) {
          _footer(doc, L, W);
          doc.addPage();
          rowY = 45;
        }

        try {
          doc.rect(ix, iy, imgW, imgH).lineWidth(1).stroke(BORDER);
          doc.image(r.screenshotPath, ix + 1, iy + 1, { width: imgW - 2, height: imgH - 2, cover: [imgW - 2, imgH - 2] });
        } catch (_) {
          doc.rect(ix, iy, imgW, imgH).fill(ROW_ALT);
          doc.fontSize(7).fillColor(GRAY).text("Image unavailable", ix, iy + imgH / 2 - 4, { width: imgW, align: "center" });
        }

        const sc2 = statusColor(r.status);
        doc.fontSize(6.5).fillColor(sc2).font("Helvetica-Bold")
           .text(r.status, ix, iy + imgH + 3, { width: imgW, align: "center" });
        doc.fontSize(6).fillColor(GRAY).font("Helvetica")
           .text(`${r.cameraId}  ${r.date} ${r.time}`, ix, iy + imgH + 12, { width: imgW, align: "center" });
      });
    }

    _footer(doc, L, W);
    doc.end();
  });
}

function _footer(doc, L, W) {
  const fY = doc.page.height - doc.page.margins.bottom - 6;
  doc.rect(L, fY - 6, W, 1).fill(BORDER);
  doc.fontSize(7).fillColor("#9ca3af").font("Helvetica")
     .text(
       `Stock Missing Report  •  Confidential  •  Generated ${new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}`,
       L, fY, { align: "center", width: W, lineBreak: false }
     );
}
