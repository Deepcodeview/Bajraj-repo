import { createZone, getZones, getZoneById, updateZone, deleteZone } from "./zone.service.js";

// Same store-lock pattern as employees: a store-scoped ADMIN can't act
// outside their own store, regardless of what's in the body/query.
function resolveStoreId(req, requestedStoreId) {
  if (req.user.role === "ADMIN" && req.user.storeId) {
    if (requestedStoreId && requestedStoreId !== req.user.storeId) {
      throw new Error("You are not permitted to act on a different store");
    }
    return req.user.storeId;
  }
  return requestedStoreId;
}

export async function createZoneController(req, res) {
  try {
    const storeId = resolveStoreId(req, req.body.storeId);
    const zone = await createZone(req.user.organizationId, { ...req.body, storeId });
    return res.status(201).json({ success: true, message: "Zone created successfully", data: zone });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function getZonesController(req, res) {
  try {
    const storeId = resolveStoreId(req, req.query.storeId);
    const zones = await getZones(req.user.organizationId, storeId);
    return res.status(200).json({ success: true, data: zones });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getZoneByIdController(req, res) {
  try {
    const zone = await getZoneById(req.user.organizationId, req.params.id);
    if (req.user.role === "ADMIN" && req.user.storeId && zone.store_id !== req.user.storeId) {
      return res.status(403).json({ success: false, message: "Access denied" });
    }
    return res.status(200).json({ success: true, data: zone });
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}

export async function updateZoneController(req, res) {
  try {
    const existing = await getZoneById(req.user.organizationId, req.params.id);
    if (req.user.role === "ADMIN" && req.user.storeId && existing.store_id !== req.user.storeId) {
      return res.status(403).json({ success: false, message: "Access denied" });
    }
    const zone = await updateZone(req.user.organizationId, req.params.id, req.body);
    return res.status(200).json({ success: true, message: "Zone updated successfully", data: zone });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function deleteZoneController(req, res) {
  try {
    const existing = await getZoneById(req.user.organizationId, req.params.id);
    if (req.user.role === "ADMIN" && req.user.storeId && existing.store_id !== req.user.storeId) {
      return res.status(403).json({ success: false, message: "Access denied" });
    }
    await deleteZone(req.user.organizationId, req.params.id);
    return res.status(200).json({ success: true, message: "Zone deleted successfully" });
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}
