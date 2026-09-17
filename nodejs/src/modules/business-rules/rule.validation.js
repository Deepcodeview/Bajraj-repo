export function validateCreateRule(req, res, next) {
  const { name, ruleType } = req.body;

  if (!name || !ruleType) {
    return res.status(400).json({
      success: false,
      message: "name and ruleType are required",
    });
  }

  next();
}
