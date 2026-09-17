import express from "express";

import {
  createOrganizationController,
  getOrganizationsController,
  getOrganizationByIdController,
  updateOrganizationController,
} from "./organization.controller.js";

import { authenticate, authorize } from "../../middleware/auth.middleware.js";
import { validateCreateOrganization } from "./organization.validation.js";

const router = express.Router();

router.use(authenticate);
router.use(authorize("SUPER_ADMIN"));

router.post("/", validateCreateOrganization, createOrganizationController);
router.get("/", getOrganizationsController);
router.get("/:id", getOrganizationByIdController);
router.patch("/:id", updateOrganizationController);

export default router;
