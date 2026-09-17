import { getEmployeePerformanceReport } from "./employeeReport.service.js";
import { generateEmployeeReportPdf } from "./employeeReport.pdf.js";

export async function getEmployeeReportController(req, res) {
  try {
    const { date, startDate, endDate, storeId } = req.query;
    const data = await getEmployeePerformanceReport(req.user.organizationId, { date, startDate, endDate, storeId });
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function exportEmployeeReportPdfController(req, res) {
  try {
    const { date, startDate, endDate, storeId } = req.query;
    const report = await getEmployeePerformanceReport(req.user.organizationId, { date, startDate, endDate, storeId });
    const pdfBuffer = await generateEmployeeReportPdf(report);
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="employee-performance-${date || startDate || "today"}.pdf"`);
    return res.send(pdfBuffer);
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}
