import express from 'express';
import { authenticate, authorize } from '../../middleware/auth.middleware.js';
import { getCamerasController, getCameraByIdController, createCameraController, updateCameraController, deleteCameraController } from './camera.controller.js';

const router = express.Router();
router.use(authenticate, authorize('SUPER_ADMIN', 'ADMIN'));

router.get('/',      getCamerasController);
router.get('/:id',   getCameraByIdController);
router.post('/',     createCameraController);
router.patch('/:id', updateCameraController);
router.delete('/:id',deleteCameraController);

export default router;
