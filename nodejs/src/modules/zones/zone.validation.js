const ALLOWED_ZONE_TYPES = ["SERVICE_ZONE", "BILLING_COUNTER", "STAFF_AREA", "EXIT", "ENTRANCE"];

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
