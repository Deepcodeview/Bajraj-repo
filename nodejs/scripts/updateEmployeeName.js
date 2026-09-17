import "dotenv/config";
import prisma from "../src/config/database.js";

await prisma.employees.update({
  where: { id: "2a148ec4-30b9-4b14-880a-53c8138e5bb1" },
  data: {
    first_name: "Vishal",   // ← change this
    last_name:  "Sharma",   // ← change this
  },
});

console.log("Employee name updated");
await prisma.$disconnect();
