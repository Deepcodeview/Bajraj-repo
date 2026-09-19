import express from "express";
import prisma from "../../config/database.js";

const router = express.Router();
const AI_KEY = process.env.AI_SERVICE_API_KEY || "smart-retail-ai-key-2025";

// Middleware: validate x-ai-service-key
router.use((req, res, next) => {
  if (req.headers["x-ai-service-key"] !== AI_KEY)
    return res.status(401).json({ success: false, message: "Unauthorized" });
  next();
});

// POST /api/ai-ingest/footfall
router.post("/footfall", async (req, res) => {
  try {
    const { store_id, camera_id, log_date, entries, exits, currently_inside, total_unique } = req.body;
    await prisma.footfall_logs.create({
      data: { store_id, camera_id, log_date, entries, exits, currently_inside, total_unique },
    });
    return res.json({ success: true });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// POST /api/ai-ingest/movement
router.post("/movement", async (req, res) => {
  try {
    const { store_id, global_id, camera_id, camera_name, event_type, zone,
            bbox_x1, bbox_y1, bbox_x2, bbox_y2 } = req.body;
    await prisma.person_movement_logs.create({
      data: { store_id, global_id, camera_id, camera_name, event_type, zone,
              bbox_x1, bbox_y1, bbox_x2, bbox_y2 },
    });
    return res.json({ success: true });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// POST /api/ai-ingest/alert
router.post("/alert", async (req, res) => {
  try {
    const { store_id, alert_type, severity, camera_id, zone, global_id, message, extra_data } = req.body;
    await prisma.ai_alert_logs.create({
      data: { store_id, alert_type, severity: severity || "MEDIUM", camera_id, zone,
              global_id, message, extra_data },
    });
    return res.json({ success: true });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// POST /api/ai-ingest/journey
router.post("/journey", async (req, res) => {
  try {
    const { store_id, global_id, journey, total_dwell_sec, zones_visited, entry_time, exit_time } = req.body;
    await prisma.customer_journeys.create({
      data: {
        store_id, global_id, journey, total_dwell_sec, zones_visited,
        entry_time: entry_time ? new Date(entry_time) : null,
        exit_time:  exit_time  ? new Date(exit_time)  : null,
      },
    });
    return res.json({ success: true });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// POST /api/ai-ingest/face-attendance
router.post("/face-attendance", async (req, res) => {
  try {
    const { store_id, name, attendance_date, first_seen_time, similarity, camera_id } = req.body;
    await prisma.face_attendance_logs.upsert({
      where: { uq_face_attendance_per_day: { store_id, name, attendance_date } },
      create: { store_id, name, attendance_date,
                first_seen_time: new Date(first_seen_time), similarity, camera_id },
      update: {},  // don't overwrite if already exists
    });
    return res.json({ success: true });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// GET /api/ai-ingest/zones?camera_code=cam2
// Python backend calls this at startup to load polygon zones per camera
router.get("/zones", async (req, res) => {
  try {
    const { camera_code } = req.query;
    const where = { status: "ACTIVE", NOT: { polygon: null } };
    if (camera_code) {
      where.threshold_config = { path: ["camera_code"], equals: camera_code };
    }
    const zones = await prisma.zones.findMany({
      where,
      select: {
        id:               true,
        zone_code:        true,
        name:             true,
        zone_type:        true,
        polygon:          true,
        threshold_config: true,
      },
      orderBy: { created_at: "asc" },
    });
    return res.json({ success: true, zones });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

export default router;
