import prisma from '../../config/database.js';

export async function getCameras(organizationId, storeId) {
  return prisma.cameras.findMany({
    where: { organization_id: organizationId, ...(storeId && { store_id: storeId }) },
    orderBy: { created_at: 'desc' },
  });
}

export async function getCameraById(organizationId, id) {
  const cam = await prisma.cameras.findFirst({ where: { id, organization_id: organizationId } });
  if (!cam) throw new Error('Camera not found');
  return cam;
}

export async function createCamera(organizationId, data) {
  const store = await prisma.stores.findFirst({ where: { id: data.storeId, organization_id: organizationId } });
  if (!store) throw new Error('Store not found');
  return prisma.cameras.create({
    data: {
      organization_id: organizationId,
      store_id: data.storeId,
      zone_id: data.zoneId || null,
      camera_code: data.cameraCode,
      name: data.name,
      stream_reference: data.streamReference || null,
      resolution: data.resolution || null,
      fps: data.fps ? parseFloat(data.fps) : null,
      status: data.status || 'ACTIVE',
      health_status: 'OFFLINE',
    },
  });
}

export async function updateCamera(organizationId, id, data) {
  await getCameraById(organizationId, id);
  const updateData = {};
  if (data.name !== undefined) updateData.name = data.name;
  if (data.streamReference !== undefined) updateData.stream_reference = data.streamReference;
  if (data.resolution !== undefined) updateData.resolution = data.resolution;
  if (data.fps !== undefined) updateData.fps = data.fps ? parseFloat(data.fps) : null;
  if (data.status !== undefined) updateData.status = data.status;
  if (data.zoneId !== undefined) updateData.zone_id = data.zoneId || null;
  updateData.updated_at = new Date();
  return prisma.cameras.update({ where: { id }, data: updateData });
}

export async function deleteCamera(organizationId, id) {
  await getCameraById(organizationId, id);
  await prisma.cameras.delete({ where: { id } });
}
