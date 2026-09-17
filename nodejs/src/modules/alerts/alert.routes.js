import express from "express";

import {
  evaluateUnattendedCustomerController,
  getAlertsController,
  getAlertByIdController,
  acknowledgeAlertController,
  resolveAlertController,
} from "./alert.controller.js";

import { getAlertReportController, exportAlertReportPdfController } from "./alertReport.controller.js";

import { authenticate, authorize } from "../../middleware/auth.middleware.js";
import { validateResolveAlert } from "./alert.validation.js";

const router = express.Router();

router.use(authenticate);
router.use(authorize("SUPER_ADMIN", "ADMIN"));

// Manual trigger for now — swap/extend this call site later once the
// AI team's detection trigger mechanism (webhook vs poll) is decided.
router.post("/evaluate/unattended/:sessionId", evaluateUnattendedCustomerController);

router.get("/report",            getAlertReportController);
router.get("/report/export/pdf", exportAlertReportPdfController);

router.get("/", getAlertsController);
router.get("/:id", getAlertByIdController);
router.patch("/:id/acknowledge", acknowledgeAlertController);
router.patch("/:id/resolve", validateResolveAlert, resolveAlertController);

export default router;
