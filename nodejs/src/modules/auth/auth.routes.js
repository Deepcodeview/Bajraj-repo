import express from "express";

import {
  loginController,
  meController,
} from "./auth.controller.js";

import {
  createAdminController,
} from "./admin.controller.js";

import {
  authenticate,
  authorize,
} from "../../middleware/auth.middleware.js";

const router = express.Router();

router.post("/login", loginController);

router.get(
  "/me",
  authenticate,
  meController
);

router.post(
  "/admins",
  authenticate,
  authorize("SUPER_ADMIN"),
  createAdminController
);

export default router;