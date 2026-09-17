import express from "express";
import { createEmployeeController, getEmployeesController, getEmployeeByIdController, updateEmployeeController, deleteEmployeeController } from "./employee.controller.js";
import { getEmployeeReportController, exportEmployeeReportPdfController } from "./employeeReport.controller.js";
import { authenticate, authorize } from "../../middleware/auth.middleware.js";
import { validateCreateEmployee, validateUpdateEmployee } from "./employee.validation.js";

const router = express.Router();

router.use(authenticate, authorize("SUPER_ADMIN", "ADMIN"));

router.get("/report",            getEmployeeReportController);
router.get("/report/export/pdf", exportEmployeeReportPdfController);

router.post("/", validateCreateEmployee, createEmployeeController);
router.get("/", getEmployeesController);
router.get("/:id", getEmployeeByIdController);
router.patch("/:id", validateUpdateEmployee, updateEmployeeController);
router.put("/:id", validateUpdateEmployee, updateEmployeeController);
router.delete("/:id", deleteEmployeeController);

export default router;
