import "dotenv/config";
import prisma from "../src/config/database.js";

await prisma.employees.update({
  where: { id: "2a148ec4-30b9-4b14-880a-53c8138e5bb1" },
  data: { employee_code: "EMP0001" },
});

console.log("employee_code updated to EMP0001");
await prisma.$disconnect();
