const ALLOWED_ZONE_TYPES = [
  "SERVICE_ZONE", "BILLING_COUNTER", "STAFF_AREA", "EXIT", "ENTRANCE",
  "GENERAL", "QUEUE", "RESTRICTED", "SHELF", "LOITERING",
];

export function validateCreateZone(req, res, next) {
  const { storeId, zoneCode, name, zoneType } = req.body;

  if (!storeId || !zoneCode || !name || !zoneType) {
    return res.status(400).json({
      success: false,
      message: "storeId, zoneCode, name, and zoneType are required",
    });
  }

  if (!ALLOWED_ZONE_TYPES.includes(zoneType)) {
    return res.status(400).json({
      success: false,
      message: `zoneType must be one of: ${ALLOWED_ZONE_TYPES.join(", ")}`,
    });
  }

  next();
}

export function validateUpdatePolygon(req, res, next) {
  const { polygon } = req.body;
  if (!polygon || !Array.isArray(polygon) || polygon.length < 3) {
    return res.status(400).json({
      success: false,
      message: "polygon must be an array of at least 3 points: [{x, y}, ...]",
    });
  }
  for (const pt of polygon) {
    if (typeof pt.x !== "number" || typeof pt.y !== "number" ||
        pt.x < 0 || pt.x > 1 || pt.y < 0 || pt.y > 1) {
      return res.status(400).json({
        success: false,
        message: "Each polygon point must have x and y as normalized floats (0.0 – 1.0)",
      });
    }
  }
  next();
}
