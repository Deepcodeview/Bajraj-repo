import prisma from "../../config/database.js";
import { getAttendanceReport } from "../attendance/attendance.service.js";
import { generateAttendancePdf } from "../attendance/attendance.pdf.js";

const PYTHON_URL = process.env.PYTHON_BACKEND_URL || "http://localhost:8001";

// In-memory report store (replace with DB table if needed)
const _reports    = [];
const _scheduled  = [];
let   _reportId   = 1;

// ── Summary (top cards) ───────────────────────────────────────────────────────

export async function getReportsSummary(organizationId) {
  const org = await prisma.organizations.findFirst({ where: { id: organizationId } });
  const total     = _reports.filter(r => r.organizationId === organizationId).length;
  const scheduled = _scheduled.filter(r => r.organizationId === organizationId).length;
  const last      = _reports.filter(r => r.organizationId === organizationId).slice(-1)[0];

  return {
    organization:      { id: org.id, name: org.name },
    totalGenerated:    total,
    scheduledReports:  scheduled,
    lastReport:        last ? { name: last.name, generatedAt: last.generatedAt } : null,
    mostRequested:     "Attendance Report",
  };
}

// ── Report History ────────────────────────────────────────────────────────────

export async function getReportsHistory(organizationId, { type, page = 1, limit = 20 }) {
  let list = _reports.filter(r => r.organizationId === organizationId);
  if (type) list = list.filter(r => r.type === type);
  list = list.slice().reverse();
  const total = list.length;
  const data  = list.slice((page - 1) * limit, page * limit);
  return { total, page, limit, reports: data };
}

// ── Generate Report ───────────────────────────────────────────────────────────

export async function generateReport(organizationId, { type, startDate, endDate, date, storeId }) {
  const org = await prisma.organizations.findFirst({ where: { id: organizationId } });

  let fileSize = "0 KB";
  let pdfBuffer = null;

  if (type === "attendance" || type === "Attendance") {
    const report  = await getAttendanceReport(organizationId, { startDate, endDate, date, storeId });
    pdfBuffer     = await generateAttendancePdf(report);
    fileSize      = `${(pdfBuffer.length / 1024).toFixed(1)} KB`;
  } else if (type === "footfall" || type === "Footfall") {
    pdfBuffer = await generateFootfallPdf({ startDate, endDate, date });
    fileSize  = `${(pdfBuffer.length / 1024).toFixed(1)} KB`;
  }

  const record = {
    id:             _reportId++,
    organizationId,
    name:           `${type} Report`,
    type,
    dateRange:      date || `${startDate} - ${endDate}`,
    generatedAt:    new Date().toISOString(),
    generatedBy:    org.name,
    fileSize,
    status:         "Ready",
    pdfBuffer,
  };

  _reports.push(record);

  return {
    id:          record.id,
    name:        record.name,
    type:        record.type,
    dateRange:   record.dateRange,
    generatedAt: record.generatedAt,
    fileSize:    record.fileSize,
    status:      record.status,
  };
}

// ── Download Report ───────────────────────────────────────────────────────────

export async function getReportById(organizationId, id) {
  const report = _reports.find(r => r.organizationId === organizationId && r.id === parseInt(id));
  if (!report) throw new Error("Report not found");
  return report;
}

// ── Scheduled Reports ─────────────────────────────────────────────────────────

export async function getScheduledReports(organizationId) {
  return _scheduled.filter(r => r.organizationId === organizationId);
}

export async function createScheduledReport(organizationId, { name, type, frequency, recipients }) {
  const record = {
    id:             _reportId++,
    organizationId,
    name,
    type,
    frequency,
    recipients,
    status:         "Active",
    createdAt:      new Date().toISOString(),
    nextRun:        getNextRun(frequency),
  };
  _scheduled.push(record);
  return record;
}

function getNextRun(frequency) {
  const d = new Date();
  if (frequency === "daily")   d.setDate(d.getDate() + 1);
  if (frequency === "weekly")  d.setDate(d.getDate() + 7);
  if (frequency === "monthly") d.setMonth(d.getMonth() + 1);
  return d.toISOString();
}

// ── Footfall helpers ──────────────────────────────────────────────────────────

export async function getFootfallSummary({ date, startDate, endDate } = {}) {
  try {
    if (date || (!startDate && !endDate)) {
      const d = date || new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
      const res = await fetch(`${PYTHON_URL}/footfall/today`);
      if (!res.ok) return null;
      return await res.json();
    }
    const res = await fetch(`${PYTHON_URL}/footfall/range?start_date=${startDate}&end_date=${endDate}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function generateFootfallPdf({ date, startDate, endDate }) {
  const { default: PDFDocument } = await import("pdfkit");
  const data = await getFootfallSummary({ date, startDate, endDate });

  return new Promise((resolve, reject) => {
    const doc    = new PDFDocument({ margin: 50 });
    const chunks = [];
    doc.on("data", c => chunks.push(c));
    doc.on("end",  () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);

    doc.fontSize(20).fillColor("#0057ff").text("Footfall Report", { align: "center" });
    doc.moveDown(0.5);
    doc.fontSize(11).fillColor("#64748b")
       .text(`Generated: ${new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}`, { align: "center" });
    doc.moveDown();

    if (!data) {
      doc.fontSize(12).fillColor("red").text("Could not fetch footfall data from AI service.");
      doc.end();
      return;
    }

    if (data.daily) {
      // Range report
      doc.fontSize(13).fillColor("#0f1923").text(`Period: ${data.start_date} → ${data.end_date}`);
      doc.moveDown(0.5);
      const totalEntries = data.daily.reduce((s, d) => s + d.entries, 0);
      const totalUnique  = data.daily.reduce((s, d) => s + d.total_unique, 0);
      doc.fontSize(12).fillColor("#334155")
         .text(`Total Visitors (entries): ${totalEntries}`)
         .text(`Total Unique People:      ${totalUnique}`);
      doc.moveDown();
      doc.fontSize(11).fillColor("#0057ff").text("Daily Breakdown:");
      doc.moveDown(0.3);
      for (const row of data.daily) {
        doc.fontSize(10).fillColor("#334155")
           .text(`  ${row.date}   Entries: ${row.entries}   Unique: ${row.total_unique}`);
      }
    } else {
      // Today report
      doc.fontSize(13).fillColor("#0f1923").text(`Date: ${data.date}`);
      doc.moveDown(0.5);
      doc.fontSize(12).fillColor("#334155")
         .text(`Total Visitors (entries): ${data.total_entries}`)
         .text(`Total Unique People:      ${data.total_unique}`)
         .text(`Currently Inside:         ${data.currently_inside}`);
      if (data.cameras?.length) {
        doc.moveDown();
        doc.fontSize(11).fillColor("#0057ff").text("Per Camera:");
        doc.moveDown(0.3);
        for (const cam of data.cameras) {
          doc.fontSize(10).fillColor("#334155")
             .text(`  ${cam.camera_id}   Entries: ${cam.entries}   Inside: ${cam.currently_inside}`);
        }
      }
    }

    doc.end();
  });
}
