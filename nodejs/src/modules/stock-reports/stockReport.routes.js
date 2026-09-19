import express from "express";
import { authenticate, authorize, authenticateAiService } from "../../middleware/auth.middleware.js";
import { createStockReportController, getStockReportsController, getStockReportSummaryController, downloadStockReportPdfController } from "./stockReport.controller.js";

const router = express.Router();

// Python AI backend posts here — API key auth
router.post("/",           authenticateAiService, createStockReportController);

// Dashboard reads — JWT auth
router.get("/summary",     authenticate, authorize("SUPER_ADMIN"), getStockReportSummaryController);
router.get("/export/pdf",  authenticate, authorize("SUPER_ADMIN"), downloadStockReportPdfController);
router.get("/",            authenticate, authorize("SUPER_ADMIN"), getStockReportsController);

export default router;
