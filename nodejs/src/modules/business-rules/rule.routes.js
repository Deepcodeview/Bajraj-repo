import express from "express";

import {
  createRuleController,
  getRulesController,
  getRuleByIdController,
  updateRuleController,
} from "./rule.controller.js";

import { authenticate, authorize } from "../../middleware/auth.middleware.js";
import { validateCreateRule } from "./rule.validation.js";

const router = express.Router();

router.use(authenticate);
router.use(authorize("SUPER_ADMIN", "ADMIN"));

router.post("/", validateCreateRule, createRuleController);
router.get("/", getRulesController);
router.get("/:id", getRuleByIdController);
router.patch("/:id", updateRuleController);

export default router;
