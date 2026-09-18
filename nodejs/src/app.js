import express from "express";
import cors from "cors";
import helmet from "helmet";
import morgan from "morgan";

import authRoutes from "./modules/auth/auth.routes.js";
import storeRoutes from "./modules/stores/store.routes.js";
import employeeRoutes from "./modules/employees/employee.routes.js";
import attendanceRoutes from "./modules/attendance/attendance.routes.js";
import customerSessionRoutes from "./modules/customer-sessions/customerSession.routes.js";
import ruleRoutes from "./modules/business-rules/rule.routes.js";
import alertRoutes from "./modules/alerts/alert.routes.js";
import organizationRoutes from "./modules/organizations/organization.routes.js";
import zoneRoutes from "./modules/zones/zone.routes.js";
import reportRoutes from "./modules/reports/report.routes.js";

const app = express();

app.use(helmet());
app.use(cors({
  origin: ["http://localhost:5173", "http://localhost:3000"],
  credentials: true,
}));
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (req, res) => {
  res.json({ status: "ok", message: "Bachraj Smart Retail Backend is running" });
});

app.use("/api/auth", authRoutes);
app.use("/api/stores", storeRoutes);
app.use("/api/employees", employeeRoutes);
app.use("/api/attendance", attendanceRoutes);
app.use("/api/customer-sessions", customerSessionRoutes);
app.use("/api/rules", ruleRoutes);
app.use("/api/alerts", alertRoutes);
app.use("/api/organizations", organizationRoutes);
app.use("/api/zones", zoneRoutes);
app.use("/api/reports", reportRoutes);

export default app;