import prisma from "../../config/database.js";

// NOTE: Unlike every other service in this codebase, these functions are
// NOT scoped by organizationId — organizations ARE the top-level entity.
// Only SUPER_ADMIN routes should ever reach these (enforced in routes).

export async function createOrganization(data) {
  const existingOrg = await prisma.organizations.findUnique({
    where: { organization_code: data.organizationCode },
  });

  if (existingOrg) {
    throw new Error("Organization code already exists");
  }

  const organization = await prisma.organizations.create({
    data: {
      organization_code: data.organizationCode,
      name: data.name,
      legal_name: data.legalName || data.name,
      email: data.email || null,
      country: data.country || "India",
      timezone: data.timezone || "Asia/Kolkata",
      status: "ACTIVE",
    },
  });

  return organization;
}

export async function getOrganizations() {
  return prisma.organizations.findMany({
    orderBy: { created_at: "desc" },
  });
}

export async function getOrganizationById(organizationId) {
  const organization = await prisma.organizations.findUnique({
    where: { id: organizationId },
  });

  if (!organization) {
    throw new Error("Organization not found");
  }

  return organization;
}

export async function updateOrganization(organizationId, data) {
  await getOrganizationById(organizationId); // throws if not found

  const updateData = {};
  if (data.name !== undefined) updateData.name = data.name;
  if (data.legalName !== undefined) updateData.legal_name = data.legalName;
  if (data.email !== undefined) updateData.email = data.email;
  if (data.country !== undefined) updateData.country = data.country;
  if (data.timezone !== undefined) updateData.timezone = data.timezone;
  if (data.status !== undefined) updateData.status = data.status; // "ACTIVE" | "INACTIVE"

  return prisma.organizations.update({
    where: { id: organizationId },
    data: updateData,
  });
}
