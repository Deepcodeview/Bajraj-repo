import { getReportsSummary, getReportsHistory, generateReport, getReportById, getScheduledReports, createScheduledReport } from "./report.service.js";

export async function getReportsSummaryController(req, res) {
  try {
    const data = await getReportsSummary(req.user.organizationId);
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getReportsHistoryController(req, res) {
  try {
    const { type, page, limit } = req.query;
    const data = await getReportsHistory(req.user.organizationId, { type, page: parseInt(page || 1), limit: parseInt(limit || 20) });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function generateReportController(req, res) {
  try {
    const { type, startDate, endDate, date, storeId } = req.body;
    if (!type) return res.status(400).json({ success: false, message: "type is required" });
    const data = await generateReport(req.user.organizationId, { type, startDate, endDate, date, storeId });
    return res.status(201).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function downloadReportController(req, res) {
  try {
    const report = await getReportById(req.user.organizationId, req.params.id);
    if (!report.pdfBuffer) return res.status(404).json({ success: false, message: "PDF not available" });
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="${report.name.replace(/ /g, "-")}.pdf"`);
    return res.send(report.pdfBuffer);
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}

export async function getScheduledReportsController(req, res) {
  try {
    const data = await getScheduledReports(req.user.organizationId);
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function createScheduledReportController(req, res) {
  try {
    const { name, type, frequency, recipients } = req.body;
    if (!name || !type || !frequency) return res.status(400).json({ success: false, message: "name, type and frequency are required" });
    const data = await createScheduledReport(req.user.organizationId, { name, type, frequency, recipients });
    return res.status(201).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}
