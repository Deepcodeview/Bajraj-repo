import express from "express";
import { authenticateAiService, authenticate, authorize } from "../../middleware/auth.middleware.js";
import { validateAiEvent } from "./attendance.validation.js";
import { aiEventController, getReportController, getReportSummaryController, getReportTrendController, getLiveLogController, exportReportPdfController } from "./attendance.controller.js";

const router = express.Router();

router.post("/ai-event", authenticateAiService, validateAiEvent, aiEventController);

router.use(authenticate, authorize("SUPER_ADMIN"));
router.get("/report", getReportController);
router.get("/report/summary", getReportSummaryController);
router.get("/report/trend", getReportTrendController);
router.get("/report/live-log", getLiveLogController);
router.get("/report/export/pdf", exportReportPdfController);

export default router;
