import { saveStockReport, getStockReports, getStockReportSummary } from "./stockReport.service.js";
import { generateStockReportPdf } from "./stockReport.pdf.js";

export function createStockReportController(req, res) {
  try {
    const record = saveStockReport(req.body);
    return res.status(201).json({ success: true, data: record });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
}

export function getStockReportsController(req, res) {
  try {
    const { cameraId, status, date, page, limit } = req.query;
    const data = getStockReports({
      cameraId, status, date,
      page:  parseInt(page  || 1),
      limit: parseInt(limit || 20),
    });
    return res.status(200).json({ success: true, data });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
}

export function getStockReportSummaryController(req, res) {
  try {
    return res.status(200).json({ success: true, data: getStockReportSummary() });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
}

export async function downloadStockReportPdfController(req, res) {
  try {
    const { cameraId, status, date } = req.query;
    const today     = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    const filterDate = date || today;
    const { reports } = getStockReports({ cameraId, status, date: filterDate, limit: 100 });
    const summary     = getStockReportSummary();
    const org         = { name: req.user?.organizationName || "Smart Retail" };
    const dateRange   = `${filterDate}`;

    const pdfBuffer = await generateStockReportPdf({ organization: org, summary, reports, dateRange });

    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="stock-report-${filterDate}.pdf"`);
    return res.send(pdfBuffer);
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
}
