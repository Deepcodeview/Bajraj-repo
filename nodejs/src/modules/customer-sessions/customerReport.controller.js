import { getCustomerReport, getCustomerSummary } from "./customerReport.service.js";
import { generateCustomerReportPdf } from "./customerReport.pdf.js";

export async function getCustomerReportController(req, res) {
  try {
    const { date, startDate, endDate, storeId } = req.query;
    const data = await getCustomerReport(req.user.organizationId, { date, startDate, endDate, storeId });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getCustomerSummaryController(req, res) {
  try {
    const { date, storeId } = req.query;
    const data = await getCustomerSummary(req.user.organizationId, { date, storeId });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function exportCustomerReportPdfController(req, res) {
  try {
    const { date, startDate, endDate, storeId } = req.query;
    const report = await getCustomerReport(req.user.organizationId, { date, startDate, endDate, storeId });
    const pdfBuffer = await generateCustomerReportPdf(report);
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="customer-report-${date || startDate || "today"}.pdf"`);
    return res.send(pdfBuffer);
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}
