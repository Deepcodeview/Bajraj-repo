import prisma from "../../config/database.js";
import { getAttendanceReport } from "../attendance/attendance.service.js";
import { generateAttendancePdf } from "../attendance/attendance.pdf.js";
import { getSalesReport } from "./sales.service.js";
import { generateSalesPdf } from "./sales.pdf.js";

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
  }

  if (type === "sales" || type === "Sales") {
    const report  = await getSalesReport(organizationId, { startDate, endDate, storeId });
    pdfBuffer     = await generateSalesPdf(report);
    fileSize      = `${(pdfBuffer.length / 1024).toFixed(1)} KB`;
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
