import bcrypt from "bcryptjs";
import prisma from "../../config/database.js";

export async function createAdmin(organizationId, data) {
  const email = data.email.toLowerCase();

  const existingUser = await prisma.users.findFirst({
    where: {
      organization_id: organizationId,
      email,
    },
  });

  if (existingUser) {
    throw new Error("User with this email already exists");
  }

  const existingCode = await prisma.users.findFirst({
    where: {
      organization_id: organizationId,
      user_code: data.userCode,
    },
  });

  if (existingCode) {
    throw new Error("User code already exists");
  }

  const adminRole = await prisma.roles.findFirst({
    where: {
      code: "ADMIN",
      OR: [
        { organization_id: organizationId },
        { organization_id: null },
      ],
    },
  });

  if (!adminRole) {
    throw new Error("ADMIN role not found");
  }

  // Optional: scope this admin to a single store. Leave storeId out to
  // create an org-wide admin (sees everything in the organization).
  let storeId = null;
  if (data.storeId) {
    const store = await prisma.stores.findFirst({
      where: { id: data.storeId, organization_id: organizationId },
    });
    if (!store) {
      throw new Error("Store not found for this organization");
    }
    storeId = store.id;
  }

  const passwordHash = await bcrypt.hash(data.password, 10);

  const admin = await prisma.users.create({
    data: {
      organization_id: organizationId,
      store_id: storeId,
      user_code: data.userCode,
      first_name: data.firstName,
      last_name: data.lastName || null,
      email,
      phone: data.phone || null,
      password_hash: passwordHash,
      status: "ACTIVE",

      user_roles: {
        create: {
          role_id: adminRole.id,
        },
      },
    },
    include: {
      user_roles: {
        include: {
          roles: true,
        },
      },
    },
  });

  return {
    id: admin.id,
    userCode: admin.user_code,
    firstName: admin.first_name,
    lastName: admin.last_name,
    email: admin.email,
    phone: admin.phone,
    organizationId: admin.organization_id,
    storeId: admin.store_id,
    role: admin.user_roles[0]?.roles?.code,
    status: admin.status,
  };
}