import bcrypt from 'bcryptjs';
import { PrismaClient } from '../generated/prisma/index.js';

const prisma = new PrismaClient();

async function seed() {
  console.log('🌱 Starting seed...\n');

  // ── 1. Ensure organization exists ─────────────────────────────────
  let org = await prisma.organizations.findFirst({
    where: { organization_code: 'BACHRAJ' },
  });

  if (!org) {
    org = await prisma.organizations.create({
      data: {
        organization_code: 'BACHRAJ',
        name: 'Bachraj Smart Retail',
        email: 'admin@bachraj.com',
        status: 'ACTIVE',
      },
    });
    console.log('✅ Organization created:', org.name);
  } else {
    console.log('✅ Organization found:', org.name);
  }

  // ── 2. Ensure SUPER_ADMIN role exists ─────────────────────────────
  let role = await prisma.roles.findFirst({
    where: { code: 'SUPER_ADMIN' },
  });

  if (!role) {
    role = await prisma.roles.create({
      data: {
        organization_id: org.id,
        name: 'Super Admin',
        code: 'SUPER_ADMIN',
        is_system_role: true,
      },
    });
    console.log('✅ Role created: SUPER_ADMIN');
  } else {
    console.log('✅ Role found: SUPER_ADMIN');
  }

  // ── 3. Upsert superadmin user ─────────────────────────────────────
  const plainPassword = 'Admin@123';
  const password_hash = await bcrypt.hash(plainPassword, 10);

  let user = await prisma.users.findFirst({
    where: { organization_id: org.id, email: 'superadmin@bachraj.com' },
  });

  if (!user) {
    user = await prisma.users.create({
      data: {
        organization_id: org.id,
        user_code: 'SA001',
        first_name: 'Super',
        last_name: 'Admin',
        email: 'superadmin@bachraj.com',
        password_hash,
        status: 'ACTIVE',
      },
    });
    console.log('✅ User created:', user.email);
  } else {
    user = await prisma.users.update({
      where: { id: user.id },
      data: { password_hash, status: 'ACTIVE' },
    });
    console.log('✅ User password reset:', user.email);
  }

  // ── 4. Ensure role is assigned ────────────────────────────────────
  const existing = await prisma.user_roles.findFirst({
    where: { user_id: user.id, role_id: role.id },
  });

  if (!existing) {
    await prisma.user_roles.create({
      data: { user_id: user.id, role_id: role.id },
    });
    console.log('✅ Role assigned to user');
  } else {
    console.log('✅ Role already assigned');
  }

  console.log('\n─────────────────────────────────────');
  console.log('🎉 Seed complete! Login credentials:');
  console.log('   Email   :', user.email);
  console.log('   Password:', plainPassword);
  console.log('─────────────────────────────────────\n');
}

seed()
  .catch((e) => { console.error('❌ Seed failed:', e.message); process.exit(1); })
  .finally(() => prisma.$disconnect());
