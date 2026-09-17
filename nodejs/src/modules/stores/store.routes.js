import express from "express";

import {
  createStoreController,
  getStoresController,
  getStoreByIdController,
} from "./store.controller.js";

import {
  authenticate,
  authorize,
} from "../../middleware/auth.middleware.js";

import {
  validateCreateStore,
} from "./store.validation.js";

const router = express.Router();

router.use(authenticate);

router.post(
  "/",
  authorize("SUPER_ADMIN"),
  validateCreateStore,
  createStoreController
);

router.get(
  "/",
  authorize("SUPER_ADMIN"),
  getStoresController
);

router.get(
  "/:id",
  authorize("SUPER_ADMIN"),
  getStoreByIdController
);

export default router;