import { getCameras, getCameraById, createCamera, updateCamera, deleteCamera } from './camera.service.js';

export async function getCamerasController(req, res) {
  try {
    const data = await getCameras(req.user.organizationId, req.query.storeId);
    res.json({ success: true, data });
  } catch (e) { res.status(500).json({ success: false, message: e.message }); }
}

export async function getCameraByIdController(req, res) {
  try {
    const data = await getCameraById(req.user.organizationId, req.params.id);
    res.json({ success: true, data });
  } catch (e) { res.status(404).json({ success: false, message: e.message }); }
}

export async function createCameraController(req, res) {
  try {
    const data = await createCamera(req.user.organizationId, req.body);
    res.status(201).json({ success: true, data });
  } catch (e) { res.status(400).json({ success: false, message: e.message }); }
}

export async function updateCameraController(req, res) {
  try {
    const data = await updateCamera(req.user.organizationId, req.params.id, req.body);
    res.json({ success: true, data });
  } catch (e) { res.status(400).json({ success: false, message: e.message }); }
}

export async function deleteCameraController(req, res) {
  try {
    await deleteCamera(req.user.organizationId, req.params.id);
    res.json({ success: true, message: 'Camera deleted' });
  } catch (e) { res.status(400).json({ success: false, message: e.message }); }
}
