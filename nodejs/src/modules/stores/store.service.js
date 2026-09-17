import prisma from "../../config/database.js";

export async function createStore(organizationId, data) {
  const existingStore = await prisma.stores.findFirst({
    where: {
      organization_id: organizationId,
      store_code: data.storeCode,
    },
  });

  if (existingStore) {
    throw new Error("Store code already exists");
  }

  const store = await prisma.stores.create({
    data: {
      organization_id: organizationId,
      store_code: data.storeCode,
      name: data.name,
      address_line1: data.addressLine1 || null,
      address_line2: data.addressLine2 || null,
      city: data.city || null,
      state: data.state || null,
      country: data.country || "India",
      postal_code: data.postalCode || null,
      latitude: data.latitude || null,
      longitude: data.longitude || null,
      timezone: data.timezone || "Asia/Kolkata",
      status: "ACTIVE",
    },
  });

  return store;
}

export async function getStores(organizationId) {
  return prisma.stores.findMany({
    where: {
      organization_id: organizationId,
    },
    orderBy: {
      created_at: "desc",
    },
  });
}

export async function getStoreById(organizationId, storeId) {
  const store = await prisma.stores.findFirst({
    where: {
      id: storeId,
      organization_id: organizationId,
    },
  });

  if (!store) {
    throw new Error("Store not found");
  }

  return store;
}