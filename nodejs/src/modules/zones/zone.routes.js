import express from "express";

import {
  createZoneController,
  getZonesController,
  getZoneByIdController,
  updateZoneController,
  updateZonePolygonController,
  deleteZoneController,
} from "./zone.controller.js";

import { authenticate, authorize } from "../../middleware/auth.middleware.js";
import { validateCreateZone, validateUpdatePolygon } from "./zone.validation.js";

const router = express.Router();

router.use(authenticate, authorize("SUPER_ADMIN", "ADMIN"));

router.post("/",                  validateCreateZone,   createZoneController);
router.get("/",                                         getZonesController);
router.get("/:id",                                      getZoneByIdController);
router.patch("/:id",                                    updateZoneController);
router.patch("/:id/polygon",      validateUpdatePolygon, updateZonePolygonController);
router.delete("/:id",                                   deleteZoneController);

export default router;
