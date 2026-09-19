import prisma from "../../config/database.js";

async function assertStoreBelongsToOrganization(organizationId, storeId) {
  const store = await prisma.stores.findFirst({
    where: { id: storeId, organization_id: organizationId },
  });
  if (!store) throw new Error("Store not found in this organization");
}

export async function createZone(organizationId, data) {
  await assertStoreBelongsToOrganization(organizationId, data.storeId);

  const existingCode = await prisma.zones.findFirst({
    where: { store_id: data.storeId, zone_code: data.zoneCode },
  });
  if (existingCode) {
    throw new Error("Zone code already exists for this store");
  }

  return prisma.zones.create({
    data: {
      organization_id: organizationId,
      store_id:        data.storeId,
      zone_code:       data.zoneCode,
      name:            data.name,
      zone_type:       data.zoneType,
      polygon:         data.polygon   || null,
      threshold_config: data.thresholdConfig || null,
      status: "ACTIVE",
    },
  });
}

export async function getZones(organizationId, storeId, cameraCode = null) {
  const where = { organization_id: organizationId };
  if (storeId)    where.store_id  = storeId;
  // camera_code filter: zones whose zone_code starts with cameraCode prefix
  // e.g. zone_code "cam2_entrance" matches cameraCode "cam2"
  // Frontend stores camera_code in threshold_config.camera_code for flexibility
  if (cameraCode) {
    where.threshold_config = { path: ["camera_code"], equals: cameraCode };
  }

  return prisma.zones.findMany({
    where,
    orderBy: { created_at: "desc" },
  });
}

export async function getZoneById(organizationId, zoneId) {
  const zone = await prisma.zones.findFirst({
    where: { id: zoneId, organization_id: organizationId },
  });
  if (!zone) throw new Error("Zone not found");
  return zone;
}

export async function updateZone(organizationId, zoneId, data) {
  const zone = await getZoneById(organizationId, zoneId);

  const updateData = {};
  if (data.name            !== undefined) updateData.name             = data.name;
  if (data.zoneType        !== undefined) updateData.zone_type        = data.zoneType;
  if (data.polygon         !== undefined) updateData.polygon          = data.polygon;
  if (data.thresholdConfig !== undefined) updateData.threshold_config = data.thresholdConfig;
  if (data.status          !== undefined) updateData.status           = data.status;
  updateData.updated_at = new Date();

  return prisma.zones.update({
    where: { id: zone.id },
    data: updateData,
  });
}

// Dedicated polygon-only update — called from zone editor UI
export async function updateZonePolygon(organizationId, zoneId, polygon) {
  const zone = await getZoneById(organizationId, zoneId);
  return prisma.zones.update({
    where: { id: zone.id },
    data:  { polygon, updated_at: new Date() },
  });
}

export async function deleteZone(organizationId, zoneId) {
  const zone = await getZoneById(organizationId, zoneId);
  await prisma.zones.delete({ where: { id: zone.id } });
}
