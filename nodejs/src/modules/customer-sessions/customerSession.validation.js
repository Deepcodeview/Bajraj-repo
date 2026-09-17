export function validateCreateCustomerSession(req, res, next) {
  const { storeId } = req.body;

  if (!storeId) {
    return res.status(400).json({
      success: false,
      message: "storeId is required",
    });
  }

  next();
}

export function validateAssignEmployee(req, res, next) {
  const { employeeId } = req.body;

  if (!employeeId) {
    return res.status(400).json({
      success: false,
      message: "employeeId is required",
    });
  }

  next();
}

export function validateUpdateZone(req, res, next) {
  const { zoneId } = req.body;

  if (!zoneId) {
    return res.status(400).json({
      success: false,
      message: "zoneId is required",
    });
  }

  next();
}
