import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import prisma from "../../config/database.js";

export async function login(email, password) {
  const user = await prisma.users.findFirst({
    where: {
      email: email.toLowerCase(),
      status: "ACTIVE",
    },
    include: {
      user_roles: {
        include: {
          roles: true,
        },
      },
    },
  });

  if (!user) {
    throw new Error("Invalid email or password");
  }

  const passwordValid = await bcrypt.compare(
    password,
    user.password_hash
  );

  if (!passwordValid) {
    throw new Error("Invalid email or password");
  }

  const role = user.user_roles[0]?.roles?.code;

  if (!role) {
    throw new Error("User has no assigned role");
  }

  const token = jwt.sign(
    {
      userId: user.id,
      organizationId: user.organization_id,
      storeId: user.store_id || null,
      role,
    },
    process.env.JWT_SECRET,
    {
      expiresIn: process.env.JWT_EXPIRES_IN || "7d",
    }
  );

  await prisma.users.update({
    where: {
      id: user.id,
    },
    data: {
      last_login_at: new Date(),
    },
  });

  return {
    token,
    user: {
      id: user.id,
      userCode: user.user_code,
      firstName: user.first_name,
      lastName: user.last_name,
      email: user.email,
      organizationId: user.organization_id,
      storeId: user.store_id || null,
      role,
    },
  };
}