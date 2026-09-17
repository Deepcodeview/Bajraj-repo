export function validateCreateStore(req, res, next) {
  const {
    storeCode,
    name,
    addressLine1,
    addressLine2,
    city,
    state,
    country,
    postalCode,
    latitude,
    longitude,
    timezone,
  } = req.body;

  if (!storeCode || !name) {
    return res.status(400).json({
      success: false,
      message: "Store code and store name are required",
    });
  }

  next();
}