import { getAlertReport } from "./alertReport.service.js";
import { generateAlertReportPdf } from "./alertReport.pdf.js";

export async function getAlertReportController(req, res) {
  try {
    const { date, startDate, endDate, storeId, status, severity } = req.query;
    const data = await getAlertReport(req.user.organizationId, { date, startDate, endDate, storeId, status, severity });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function exportAlertReportPdfController(req, res) {
  try {
    const { date, startDate, endDate, storeId, status, severity } = req.query;
    const report = await getAlertReport(req.user.organizationId, { date, startDate, endDate, storeId, status, severity });
    const pdfBuffer = await generateAlertReportPdf(report);
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="alert-report-${date || startDate || "today"}.pdf"`);
    return res.send(pdfBuffer);
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}
