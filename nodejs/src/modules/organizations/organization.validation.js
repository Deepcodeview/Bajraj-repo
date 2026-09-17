export function validateCreateOrganization(req, res, next) {
  const { organizationCode, name } = req.body;

  if (!organizationCode || !name) {
    return res.status(400).json({
      success: false,
      message: "organizationCode and name are required",
    });
  }

  next();
}
