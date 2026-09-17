import "dotenv/config";
import prisma from "../src/config/database.js";

// The correct org — has Vishal employee + sessions
const CORRECT_ORG_ID = "3e075b20-9fb5-4910-b0a6-96d40f09097e";

async function main() {
  const user = await prisma.users.findFirst({ where: { email: "superadmin@bachraj.com" } });
  if (!user) { console.log("User not found"); return; }

  console.log("Current organization_id:", user.organization_id);

  await prisma.users.update({
    where: { id: user.id },
    data: { organization_id: CORRECT_ORG_ID },
  });

  console.log("Updated to:", CORRECT_ORG_ID);
  console.log("Done — now re-login to get a fresh JWT token");
}

main().catch(console.error).finally(() => prisma.$disconnect());
