import express from "express";

import {
  createCustomerSessionController,
  getCustomerSessionsController,
  getCustomerSessionByIdController,
  assignEmployeeController,
  updateSessionZoneController,
  endCustomerSessionController,
  getCustomerCountController,
} from "./customerSession.controller.js";

import {
  getCustomerReportController,
  getCustomerSummaryController,
  exportCustomerReportPdfController,
} from "./customerReport.controller.js";

import {
  authenticate,
  authorize,
} from "../../middleware/auth.middleware.js";

import {
  validateCreateCustomerSession,
  validateAssignEmployee,
  validateUpdateZone,
} from "./customerSession.validation.js";

const router = express.Router();

router.use(authenticate);
router.use(authorize("SUPER_ADMIN", "ADMIN"));

router.get("/count",          getCustomerCountController);
router.get("/report",            getCustomerReportController);
router.get("/report/summary",    getCustomerSummaryController);
router.get("/report/export/pdf", exportCustomerReportPdfController);

router.post("/", validateCreateCustomerSession, createCustomerSessionController);
router.get("/", getCustomerSessionsController);
router.get("/:id", getCustomerSessionByIdController);
router.patch("/:id/assign-employee", validateAssignEmployee, assignEmployeeController);
router.patch("/:id/zone", validateUpdateZone, updateSessionZoneController);
router.patch("/:id/end", endCustomerSessionController);

export default router;
