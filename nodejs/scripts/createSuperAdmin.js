import "dotenv/config";
import bcrypt from "bcryptjs";
import prisma from "../src/config/database.js";

async function main() {
  console.log("Creating Super Admin...");

  const password = "SuperAdmin@123";
  const passwordHash = await bcrypt.hash(password, 12);

  const result = await prisma.$transaction(async (tx) => {
    // 1. Find or create organization
    let organization = await tx.organizations.findUnique({
      where: {
        organization_code: "BACHRAJ",
      },
    });

    if (!organization) {
      organization = await tx.organizations.create({
        data: {
          organization_code: "BACHRAJ",
          name: "Bachraj Smart Retail",
          legal_name: "Bachraj Smart Retail",
          email: "admin@bachraj.com",
          country: "India",
          timezone: "Asia/Kolkata",
          status: "ACTIVE",
        },
      });
    }

    // 2. Find or create Super Admin role
    let role = await tx.roles.findFirst({
      where: {
        code: "SUPER_ADMIN",
      },
    });

    if (!role) {
      role = await tx.roles.create({
        data: {
          organization_id: organization.id,
          name: "Super Admin",
          code: "SUPER_ADMIN",
          description: "System Super Administrator",
          is_system_role: true,
        },
      });
    }

    // 3. Find or create Super Admin user
    let user = await tx.users.findFirst({
      where: {
        email: "superadmin@bachraj.com",
      },
    });

    if (!user) {
      user = await tx.users.create({
        data: {
          organization_id: organization.id,
          user_code: "SUPERADMIN001",
          first_name: "Super",
          last_name: "Admin",
          email: "superadmin@bachraj.com",
          password_hash: passwordHash,
          status: "ACTIVE",
        },
      });
    }

    // 4. Connect user to Super Admin role
    const existingRole = await tx.user_roles.findFirst({
      where: {
        user_id: user.id,
        role_id: role.id,
      },
    });

    if (!existingRole) {
      await tx.user_roles.create({
        data: {
          user_id: user.id,
          role_id: role.id,
        },
      });
    }

    return {
      organization,
      role,
      user,
    };
  });

  console.log("");
  console.log("=================================");
  console.log("SUPER ADMIN CREATED");
  console.log("=================================");
  console.log("Email:", result.user.email);
  console.log("Password:", password);
  console.log("Role:", result.role.code);
  console.log("Organization:", result.organization.name);
  console.log("=================================");
}

main()
  .catch((error) => {
    console.error("Failed to create Super Admin:");
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });