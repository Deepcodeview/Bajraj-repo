import {
  createRule,
  getRules,
  getRuleById,
  updateRule,
} from "./rule.service.js";

export async function createRuleController(req, res) {
  try {
    const rule = await createRule(req.user.organizationId, req.body);
    return res.status(201).json({
      success: true,
      message: "Business rule created successfully",
      data: rule,
    });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function getRulesController(req, res) {
  try {
    const rules = await getRules(req.user.organizationId, req.query);
    return res.status(200).json({ success: true, data: rules });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getRuleByIdController(req, res) {
  try {
    const rule = await getRuleById(req.user.organizationId, req.params.id);
    return res.status(200).json({ success: true, data: rule });
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}

export async function updateRuleController(req, res) {
  try {
    const rule = await updateRule(req.user.organizationId, req.params.id, req.body);
    return res.status(200).json({
      success: true,
      message: "Business rule updated successfully",
      data: rule,
    });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}
