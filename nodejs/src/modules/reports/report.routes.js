import express from "express";
import { authenticate, authorize } from "../../middleware/auth.middleware.js";
import { getReportsSummaryController, getReportsHistoryController, generateReportController, downloadReportController, getScheduledReportsController, createScheduledReportController } from "./report.controller.js";

const router = express.Router();

router.use(authenticate, authorize("SUPER_ADMIN"));

router.get("/summary",       getReportsSummaryController);
router.get("/",              getReportsHistoryController);
router.post("/generate",     generateReportController);
router.get("/export/:id",    downloadReportController);
router.get("/scheduled",     getScheduledReportsController);
router.post("/scheduled",    createScheduledReportController);

export default router;
