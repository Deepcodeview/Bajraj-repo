import "dotenv/config";
import app from "./app.js";
import prisma from "./config/database.js";

const PORT = process.env.PORT || 4000;

async function startServer() {
  try {
    await prisma.$connect();

    console.log("PostgreSQL connected successfully");

    app.listen(PORT, () => {
      console.log(`Server running on port ${PORT}`);
      console.log(`Health: http://localhost:${PORT}/health`);
    });
  } catch (error) {
    console.error("Database connection failed:");
    console.error(error);
    process.exit(1);
  }
}

startServer();