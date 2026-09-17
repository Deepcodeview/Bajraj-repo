import { processAiAttendanceEvent, getAttendanceReport, getAttendanceSummary, getAttendanceTrend, getLiveLog } from "./attendance.service.js";
import { generateAttendancePdf } from "./attendance.pdf.js";

export async function aiEventController(req, res) {
  try {
    const result = await processAiAttendanceEvent(req.body);
    return res.status(result.status).json(result.body);
  } catch (error) {
    console.error("[AI_ATTENDANCE] Unhandled error:", error.message);
    return res.status(500).json({ success: false, message: "Internal server error" });
  }
}

export async function getReportController(req, res) {
  try {
    const { startDate, endDate, date, storeId, employeeId, status } = req.query;
    const data = await getAttendanceReport(req.user.organizationId, { startDate, endDate, date, storeId, employeeId, status });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getReportSummaryController(req, res) {
  try {
    const { date, storeId } = req.query;
    const data = await getAttendanceSummary(req.user.organizationId, { date, storeId });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getReportTrendController(req, res) {
  try {
    const { storeId } = req.query;
    const data = await getAttendanceTrend(req.user.organizationId, { storeId });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getLiveLogController(req, res) {
  try {
    const { storeId, limit } = req.query;
    const data = await getLiveLog(req.user.organizationId, { storeId, limit: parseInt(limit || "20") });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function exportReportPdfController(req, res) {
  try {
    const { startDate, endDate, date, storeId } = req.query;
    const report = await getAttendanceReport(req.user.organizationId, { startDate, endDate, date, storeId });
    const pdfBuffer = await generateAttendancePdf(report);
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="attendance-report-${date || startDate || "today"}.pdf"`);
    return res.send(pdfBuffer);
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}
