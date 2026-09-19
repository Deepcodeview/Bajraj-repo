import express from "express";
import prisma from "../../config/database.js";
import { authenticate } from "../../middleware/auth.middleware.js";

const router = express.Router();
router.use(authenticate);

// GET /api/footfall/today
router.get("/today", async (req, res) => {
  try {
    const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    const rows  = await prisma.footfall_logs.findMany({ where: { log_date: today } });

    if (!rows.length)
      return res.json({ success: true, data: { date: today, total_entries: 0, total_unique: 0, currently_inside: 0, cameras: [] } });

    // Per camera: max entries, latest currently_inside
    const camMap = {};
    for (const r of rows) {
      if (!camMap[r.camera_id]) camMap[r.camera_id] = { entries: 0, exits: 0, total_unique: 0, currently_inside: 0, lastTime: null };
      const c = camMap[r.camera_id];
      c.entries      = Math.max(c.entries,      r.entries);
      c.exits        = Math.max(c.exits,         r.exits);
      c.total_unique = Math.max(c.total_unique,  r.total_unique);
      if (!c.lastTime || r.wall_time > c.lastTime) { c.currently_inside = r.currently_inside; c.lastTime = r.wall_time; }
    }

    const cameras = Object.entries(camMap).map(([camera_id, v]) => ({
      camera_id, entries: v.entries, exits: v.exits, total_unique: v.total_unique, currently_inside: v.currently_inside,
    }));

    return res.json({ success: true, data: {
      date:             today,
      total_entries:    cameras.reduce((s, c) => s + c.entries, 0),
      total_exits:      cameras.reduce((s, c) => s + c.exits, 0),
      total_unique:     cameras.reduce((s, c) => s + c.total_unique, 0),
      currently_inside: cameras.reduce((s, c) => s + c.currently_inside, 0),
      cameras,
    }});
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// GET /api/footfall/current
router.get("/current", async (req, res) => {
  try {
    const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

    // Latest row per camera
    const cameras = await prisma.$queryRaw`
      SELECT DISTINCT ON (camera_id) camera_id, currently_inside
      FROM footfall_logs
      WHERE log_date = ${today}
      ORDER BY camera_id, wall_time DESC
    `;

    const total = cameras.reduce((s, c) => s + c.currently_inside, 0);
    return res.json({ success: true, data: { currently_inside: total, cameras } });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

// GET /api/footfall/range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
router.get("/range", async (req, res) => {
  const { start_date, end_date } = req.query;
  if (!start_date || !end_date)
    return res.status(400).json({ success: false, message: "start_date and end_date required" });
  try {
    const rows = await prisma.footfall_logs.findMany({
      where: { log_date: { gte: start_date, lte: end_date } },
    });

    // Group by date+camera, take max entries, then sum per day
    const dayCam = {};
    for (const r of rows) {
      const key = `${r.log_date}__${r.camera_id}`;
      if (!dayCam[key]) dayCam[key] = { date: r.log_date, entries: 0, total_unique: 0 };
      dayCam[key].entries     = Math.max(dayCam[key].entries,     r.entries);
      dayCam[key].total_unique = Math.max(dayCam[key].total_unique, r.total_unique);
    }

    const dayTotals = {};
    for (const v of Object.values(dayCam)) {
      if (!dayTotals[v.date]) dayTotals[v.date] = { entries: 0, total_unique: 0 };
      dayTotals[v.date].entries     += v.entries;
      dayTotals[v.date].total_unique += v.total_unique;
    }

    const daily = Object.entries(dayTotals).sort().map(([date, v]) => ({ date, ...v }));
    return res.json({ success: true, data: { start_date, end_date, daily } });
  } catch (e) {
    return res.status(500).json({ success: false, message: e.message });
  }
});

export default router;
