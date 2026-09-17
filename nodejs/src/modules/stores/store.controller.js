import {
  createStore,
  getStores,
  getStoreById,
} from "./store.service.js";

export async function createStoreController(req, res) {
  try {
    const organizationId = req.body.organizationId || req.user.organizationId;
    const store = await createStore(organizationId, req.body);
    return res.status(201).json({ success: true, message: "Store created successfully", data: store });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function getStoresController(req, res) {
  try {
    const organizationId = req.query.organizationId || req.user.organizationId;
    const stores = await getStores(organizationId);
    return res.status(200).json({ success: true, data: stores });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getStoreByIdController(req, res) {
  try {
    const organizationId = req.query.organizationId || req.user.organizationId;
    const store = await getStoreById(organizationId, req.params.id);
    return res.status(200).json({ success: true, data: store });
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}