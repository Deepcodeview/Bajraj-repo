import PDFDocument from "pdfkit";

// ── Palette ──────────────────────────────────────────────────────────────────
const NAVY       = "#0b2e4f";
const BLUE       = "#1565c0";
const BLUE_DARK  = "#0d47a1";
const LIGHT_BLUE = "#eaf3fb";
const BLUE_BD    = "#bcdcf5";
const TEAL       = "#0e9aa7";
const GREEN      = "#16a34a";
const GREEN_BG   = "#f0fdf4";
const GREEN_BD   = "#bbf7d0";
const RED        = "#dc2626";
const GRAY       = "#6b7280";
const DARK       = "#101828";
const BORDER     = "#e3e8ef";
const ROW_ALT    = "#f7fafc";
const WHITE      = "#ffffff";
const HEADER_BG  = "#0d3f6e";

// Category / series colors (cycled)
const PALETTE = ["#1565c0", "#12a3a9", "#5bc0be", "#7c5cbf", "#f2994a", "#e0577b", "#64748b"];

const money = (n) => `Rs. ${Math.round(n || 0).toLocaleString("en-IN")}`;

function fmtDate(d) {
  return new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

// ── Geometry helpers for pie / donut charts ─────────────────────────────────
function polar(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function pieSlicePath(cx, cy, r, startAngle, endAngle) {
  const a1 = startAngle, a2 = Math.min(endAngle, startAngle + 359.99);
  const p1 = polar(cx, cy, r, a1);
  const p2 = polar(cx, cy, r, a2);
  const large = a2 - a1 > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${p1.x} ${p1.y} A ${r} ${r} 0 ${large} 1 ${p2.x} ${p2.y} Z`;
}

function donutSlicePath(cx, cy, rOuter, rInner, startAngle, endAngle) {
  const a1 = startAngle, a2 = Math.min(endAngle, startAngle + 359.99);
  const po1 = polar(cx, cy, rOuter, a1);
  const po2 = polar(cx, cy, rOuter, a2);
  const pi2 = polar(cx, cy, rInner, a2);
  const pi1 = polar(cx, cy, rInner, a1);
  const large = a2 - a1 > 180 ? 1 : 0;
  return `M ${po1.x} ${po1.y} A ${rOuter} ${rOuter} 0 ${large} 1 ${po2.x} ${po2.y} ` +
         `L ${pi2.x} ${pi2.y} A ${rInner} ${rInner} 0 ${large} 0 ${pi1.x} ${pi1.y} Z`;
}

function drawPie(doc, cx, cy, r, slices) {
  let angle = 0;
  slices.forEach((s, i) => {
    const sweep = (s.pct / 100) * 360;
    if (sweep > 0) {
      doc.path(pieSlicePath(cx, cy, r, angle, angle + sweep))
         .fill(s.color || PALETTE[i % PALETTE.length]);
    }
    angle += sweep;
  });
  doc.circle(cx, cy, r).lineWidth(1).stroke(WHITE);
}

function drawDonut(doc, cx, cy, rOuter, rInner, slices, centerLabel, centerValue) {
  let angle = 0;
  slices.forEach((s, i) => {
    const sweep = (s.pct / 100) * 360;
    if (sweep > 0) {
      doc.path(donutSlicePath(cx, cy, rOuter, rInner, angle, angle + sweep))
         .fill(s.color || PALETTE[i % PALETTE.length]);
    }
    angle += sweep;
  });
  doc.circle(cx, cy, rOuter).lineWidth(1).stroke(WHITE);
  doc.circle(cx, cy, rInner).lineWidth(1).stroke(WHITE);
  const tw = rOuter * 2 + 20;
  if (centerLabel) {
    doc.fontSize(6.3).fillColor(GRAY).font("Helvetica")
       .text(centerLabel, cx - tw / 2, cy - 12, { width: tw, align: "center", height: 8, ellipsis: true });
  }
  if (centerValue) {
    doc.fontSize(8.3).fillColor(DARK).font("Helvetica-Bold")
       .text(centerValue, cx - tw / 2, cy - 1, { width: tw, align: "center", height: 10, ellipsis: true, lineBreak: false });
  }
}

function legendRow(doc, x, y, color, label, value, w) {
  doc.circle(x + 4, y + 4, 4).fill(color);
  doc.fontSize(7.3).fillColor(DARK).font("Helvetica")
     .text(label, x + 13, y + 0.5, { width: w - 40, height: 9, ellipsis: true });
  doc.fontSize(7.3).fillColor(DARK).font("Helvetica-Bold")
     .text(value, x + w - 28, y + 0.5, { width: 28, align: "right", height: 9, ellipsis: true });
}

function sectionHeading(doc, x, y, w, title) {
  doc.rect(x, y, 3, 12).fill(BLUE);
  doc.fontSize(10.5).fillColor(NAVY).font("Helvetica-Bold").text(title, x + 9, y);
  doc.moveTo(x, y + 17).lineTo(x + w, y + 17).strokeColor(BORDER).lineWidth(1).stroke();
}

function panel(doc, x, y, w, h) {
  doc.rect(x, y, w, h).fill(WHITE);
  doc.rect(x, y, w, h).lineWidth(1).stroke(BORDER);
}

// ─────────────────────────────────────────────────────────────────────────────

export function generateSalesPdf(report) {
  return new Promise((resolve, reject) => {
    const doc     = new PDFDocument({ margin: 36, size: "A4" });
    const buffers = [];
    doc.on("data",  c => buffers.push(c));
    doc.on("end",   () => resolve(Buffer.concat(buffers)));
    doc.on("error", reject);

    const L  = 36;
    const PW = doc.page.width;
    const W  = PW - L * 2;
    const orgName = report.organization.name;

    // ── Header ─────────────────────────────────────────────────────────────
    const headerH = 76;
    doc.rect(L, 30, W, 3).fill(BLUE);
    doc.rect(L, 33, W, headerH).fill(NAVY);

    doc.fontSize(17).fillColor(WHITE).font("Helvetica-Bold")
       .text(orgName.toUpperCase(), L + 14, 48, { width: W * 0.5, height: 20, ellipsis: true });
    doc.fontSize(8).fillColor("#9fc2e8").font("Helvetica")
       .text("SALES PERFORMANCE REPORT", L + 14, 70, { width: W * 0.5 });

    const metaW = 220;
    const metaX = L + W - metaW;
    const metaLines = [
      ["Report Period", `${fmtDate(report.dateRange.start)} - ${fmtDate(report.dateRange.end)}`],
      ["Store(s)",       report.stores.length ? report.stores.join(", ").slice(0, 40) : "All Stores"],
      ["Currency",       "INR (Rs.)"],
      ["Generated",      new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })],
    ];
    let my = 39;
    metaLines.forEach(([k, v]) => {
      doc.fontSize(6.5).fillColor("#9fc2e8").font("Helvetica-Bold")
         .text(k, metaX, my, { width: metaW, height: 8, ellipsis: true });
      doc.fontSize(7.4).fillColor(WHITE).font("Helvetica")
         .text(v, metaX, my + 7.5, { width: metaW, height: 9, ellipsis: true });
      my += 17;
    });

    // ── KPI cards ──────────────────────────────────────────────────────────
    const cardY = 33 + headerH + 14;
    const cardH = 60;
    const gap   = 8;
    const cardW = (W - gap * 4) / 5;
    const k = report.kpis;

    const trendArrow = (pct) => (pct >= 0 ? `\u25B2 +${pct}%` : `\u25BC ${pct}%`);
    const trendColor = (pct) => (pct >= 0 ? GREEN : RED);

    const cards = [
      { label: "Total Sales",     value: money(k.totalSales),               pct: k.totalSalesChangePct },
      { label: "Total Customers", value: String(k.totalCustomers),           pct: k.totalCustomersChangePct },
      { label: "Items Sold",      value: String(Math.round(k.itemsSold)),    pct: null },
      { label: "Invoices",        value: String(k.totalInvoices),            pct: k.totalInvoicesChangePct },
      { label: "Avg Order Value", value: money(k.avgOrderValue),             pct: k.avgOrderValueChangePct },
    ];

    cards.forEach((c, i) => {
      const x = L + i * (cardW + gap);
      panel(doc, x, cardY, cardW, cardH);
      doc.rect(x, cardY, cardW, 3).fill(PALETTE[i % PALETTE.length]);
      doc.fontSize(7.3).fillColor(GRAY).font("Helvetica").text(c.label, x + 8, cardY + 10, { width: cardW - 16 });
      const valFontSize = c.value.length > 10 ? 9.5 : c.value.length > 7 ? 11 : 13.5;
      doc.fontSize(valFontSize).fillColor(NAVY).font("Helvetica-Bold").text(c.value, x + 8, cardY + 21, { width: cardW - 16, lineBreak: false, ellipsis: true });
      if (c.pct !== null) {
        doc.fontSize(7).fillColor(trendColor(c.pct)).font("Helvetica-Bold")
           .text(trendArrow(c.pct), x + 8, cardY + 41, { width: cardW - 16, height: 9, ellipsis: true, lineBreak: false });
        doc.fontSize(5.6).fillColor(GRAY).font("Helvetica")
           .text("vs previous period", x + 8, cardY + 49, { width: cardW - 16, height: 8, ellipsis: true, lineBreak: false });
      }
    });

    // ── Row: Sales Trend (bar) + Sales by Category (pie) ─────────────────────
    const row1Y = cardY + cardH + 14;
    const row1H = 152;
    const trendW = W * 0.58;
    const catW   = W - trendW - 12;

    panel(doc, L, row1Y, trendW, row1H);
    sectionHeading(doc, L + 12, row1Y + 12, trendW - 24, "Sales Trend (Last 6 Months)");

    {
      const axisW  = 46;
      const chartX = L + 14 + axisW, chartY = row1Y + 44, chartW = trendW - 34 - axisW, chartH = row1H - 76;
      const maxVal = Math.max(...report.trend.map(t => t.value), 1) * 1.18;
      const n = report.trend.length;
      const slot = chartW / n;
      const bw = Math.min(slot * 0.5, 34);

      for (let g = 0; g <= 3; g++) {
        const gy = chartY + chartH - (chartH * g) / 3;
        doc.moveTo(chartX, gy).lineTo(chartX + chartW, gy).strokeColor("#eef1f5").lineWidth(0.5).stroke();
        doc.fontSize(6).fillColor(GRAY).font("Helvetica")
           .text(money((maxVal * g) / 3), L + 14, gy - 3, { width: axisW - 6, align: "right", height: 8, ellipsis: true, lineBreak: false });
      }

      report.trend.forEach((t, i) => {
        const h = maxVal ? (t.value / maxVal) * chartH : 0;
        const x = chartX + i * slot + (slot - bw) / 2;
        const y = chartY + chartH - h;
        doc.rect(x, y, bw, Math.max(h, 1)).fill(BLUE);
        doc.fontSize(6.2).fillColor(NAVY).font("Helvetica-Bold")
           .text(money(t.value), x - 14, y - 10, { width: bw + 28, align: "center", height: 8, ellipsis: true, lineBreak: false });
        doc.fontSize(7).fillColor(GRAY).font("Helvetica")
           .text(t.label, x - 14, chartY + chartH + 5, { width: bw + 28, align: "center" });
      });
    }

    panel(doc, L + trendW + 12, row1Y, catW, row1H);
    sectionHeading(doc, L + trendW + 12 + 12, row1Y + 12, catW - 24, "Sales by Category");

    {
      const catPanelX = L + trendW + 12;
      const cx = catPanelX + 42;
      const cy = row1Y + 76;
      const r  = 34;
      const slices = report.salesByCategory.slice(0, 6).map((c, i) => ({ ...c, color: PALETTE[i % PALETTE.length] }));
      if (slices.length) {
        drawPie(doc, cx, cy, r, slices);
      } else {
        doc.fontSize(8).fillColor(GRAY).text("No category data", cx - 40, cy - 4, { width: 80, align: "center" });
      }
      let ly = row1Y + 44;
      const legendX = catPanelX + 86;
      const legendW = catW - 86 - 14;
      slices.forEach(s => {
        legendRow(doc, legendX, ly, s.color, s.name, `${s.pct}%`, legendW);
        ly += 13;
      });
    }

    // ── Row: Top Selling Products + Customer Insights ─────────────────────────
    const row2Y = row1Y + row1H + 12;
    const row2H = 146;
    const prodW = W * 0.58;
    const custW = W - prodW - 12;

    panel(doc, L, row2Y, prodW, row2H);
    sectionHeading(doc, L + 12, row2Y + 12, prodW - 24, "Top Selling Products");

    {
      const tx = L + 12, ty = row2Y + 34, tw = prodW - 24;
      const cols = [
        { label: "#",        w: 16,          align: "center" },
        { label: "Product",  w: tw * 0.34,   align: "left"   },
        { label: "Category", w: tw * 0.22,   align: "left"   },
        { label: "Units",    w: tw * 0.15,   align: "center" },
        { label: "Revenue",  w: tw - 16 - tw * 0.34 - tw * 0.22 - tw * 0.15, align: "right" },
      ];
      const rowH = 18;
      doc.rect(tx, ty, tw, rowH).fill(HEADER_BG);
      let cx = tx;
      cols.forEach(col => {
        doc.fontSize(7.2).fillColor(WHITE).font("Helvetica-Bold")
           .text(col.label, cx + 4, ty + 5.5, { width: col.w - 6, align: col.align, height: 9, ellipsis: true });
        cx += col.w;
      });
      let ry = ty + rowH;
      const list = report.topProducts.length ? report.topProducts : [];
      if (!list.length) {
        doc.fontSize(8).fillColor(GRAY).font("Helvetica")
           .text("No sales recorded for this period.", tx, ry + 10, { width: tw, align: "center" });
      }
      list.forEach((p, i) => {
        const bg = i % 2 === 0 ? WHITE : ROW_ALT;
        doc.rect(tx, ry, tw, rowH).fill(bg);
        let cx2 = tx;
        const vals = [String(i + 1), p.name, p.category, String(Math.round(p.units)), money(p.revenue)];
        cols.forEach((col, ci) => {
          doc.fontSize(7.5).fillColor(ci === 1 ? DARK : GRAY).font(ci === 1 || ci === 4 ? "Helvetica-Bold" : "Helvetica")
             .text(vals[ci], cx2 + 4, ry + 5.5, { width: col.w - 6, align: col.align, ellipsis: true });
          cx2 += col.w;
        });
        ry += rowH;
      });
    }

    panel(doc, L + prodW + 12, row2Y, custW, row2H);
    sectionHeading(doc, L + prodW + 12 + 12, row2Y + 12, custW - 24, "Customer Insights");

    {
      const ci = report.customerInsights;
      const items = [
        [String(ci.totalCustomers), "Total Customers (footfall)"],
        [`${ci.repeatPct}%`,        "Repeat Customers"],
        [`${ci.newPct}%`,           "New Customers"],
        [ci.avgVisitMinutes ? `${ci.avgVisitMinutes.toFixed(1)} min` : "--", "Avg. Visit Duration"],
      ];
      let iy = row2Y + 36;
      const ix = L + prodW + 12 + 12;
      items.forEach(([val, label]) => {
        doc.fontSize(15).fillColor(BLUE_DARK).font("Helvetica-Bold").text(val, ix, iy);
        doc.fontSize(7.3).fillColor(GRAY).font("Helvetica").text(label, ix, iy + 18);
        iy += 32;
      });
    }

    // ── Row: Billing Summary + Payment Split + Highlights ──────────────────────
    const row3Y = row2Y + row2H + 12;
    const row3H = 178;
    const billW = W * 0.30;
    const payW  = W * 0.26;
    const hiW   = W - billW - payW - 24;

    panel(doc, L, row3Y, billW, row3H);
    sectionHeading(doc, L + 12, row3Y + 12, billW - 24, "Billing Summary");
    {
      const b = report.billing;
      const rows = [
        ["Total Invoices",  String(b.totalInvoices)],
        ["Paid Invoices",   `${b.paidInvoices} (${b.paidPct}%)`],
        ["Pending Invoices",`${b.pendingInvoices} (${b.pendingPct}%)`],
        ["Total Billing",   money(b.totalBilling)],
        ["Avg. Invoice",    money(b.avgInvoice)],
        ["Highest Invoice", money(b.highestInvoice)],
        ["Lowest Invoice",  money(b.lowestInvoice)],
      ];
      let ry = row3Y + 36;
      rows.forEach(([label, val], i) => {
        if (i % 2 === 1) doc.rect(L + 6, ry - 3, billW - 12, 17).fill(ROW_ALT);
        doc.fontSize(7.6).fillColor(GRAY).font("Helvetica").text(label, L + 12, ry, { width: billW * 0.55 });
        doc.fontSize(7.6).fillColor(DARK).font("Helvetica-Bold")
           .text(val, L + 12, ry, { width: billW - 24, align: "right" });
        ry += 17;
      });
    }

    panel(doc, L + billW + 12, row3Y, payW, row3H);
    sectionHeading(doc, L + billW + 12 + 12, row3Y + 12, payW - 24, "Payment Method Split");
    {
      const cx = L + billW + 12 + payW / 2;
      const cy = row3Y + 76;
      const slices = report.paymentSplit.map((p, i) => ({ name: p.mode, pct: p.pct, color: PALETTE[i % PALETTE.length] }));
      if (slices.length) {
        drawDonut(doc, cx, cy, 40, 24, slices, "Total Billing", money(report.billing.totalBilling));
      } else {
        doc.fontSize(8).fillColor(GRAY).text("No payment data", cx - 40, cy - 4, { width: 80, align: "center" });
      }
      let ly = row3Y + 130;
      slices.forEach(s => {
        legendRow(doc, L + billW + 12 + 10, ly, s.color, s.name, `${s.pct}%`, payW - 20);
        ly += 12;
      });
    }

    const hiX = L + billW + payW + 24;
    panel(doc, hiX, row3Y, hiW, row3H);
    sectionHeading(doc, hiX + 12, row3Y + 12, hiW - 24, "Key Highlights");
    {
      let hy = row3Y + 34;
      report.highlights.slice(0, 6).forEach(h => {
        doc.circle(hiX + 14, hy + 4, 2.3).fill(GREEN);
        doc.fontSize(7.4).fillColor(DARK).font("Helvetica")
           .text(h, hiX + 20, hy, { width: hiW - 32 });
        hy += doc.heightOfString(h, { width: hiW - 32 }) + 6;
      });
    }

    // ── Footer ─────────────────────────────────────────────────────────────
    const fY = doc.page.height - doc.page.margins.bottom - 6;
    doc.rect(L, fY - 6, W, 1).fill(BORDER);
    doc.fontSize(7).fillColor("#9ca3af").font("Helvetica")
       .text(`${orgName}  \u2022  Confidential Sales Report  \u2022  Generated ${new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}`,
             L, fY, { align: "center", width: W, height: 9, ellipsis: true, lineBreak: false });

    doc.end();
  });
}
