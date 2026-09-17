const ALLOWED_EVENT_TYPES = ["FACE_RECOGNIZED"];

export function validateAiEvent(req, res, next) {
  const { eventId, cameraId, employeeId, eventType, confidence, timestamp } = req.body;

  if (!eventId || typeof eventId !== "string" || !eventId.trim())
    return res.status(400).json({ success: false, message: "eventId is required" });

  if (!cameraId || typeof cameraId !== "string" || !cameraId.trim())
    return res.status(400).json({ success: false, message: "cameraId is required" });

  if (!employeeId || typeof employeeId !== "string" || !employeeId.trim())
    return res.status(400).json({ success: false, message: "employeeId is required" });

  if (!eventType || !ALLOWED_EVENT_TYPES.includes(eventType))
    return res.status(400).json({ success: false, message: `eventType must be one of: ${ALLOWED_EVENT_TYPES.join(", ")}` });

  if (confidence === undefined || confidence === null || typeof confidence !== "number" || confidence < 0 || confidence > 1)
    return res.status(400).json({ success: false, message: "confidence must be a number between 0 and 1" });

  if (!timestamp || isNaN(Date.parse(timestamp)))
    return res.status(400).json({ success: false, message: "timestamp must be a valid ISO-8601 date string" });

  next();
}
