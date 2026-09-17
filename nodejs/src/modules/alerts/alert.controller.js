import {
  evaluateUnattendedCustomer,
  getAlerts,
  getAlertById,
  acknowledgeAlert,
  resolveAlert,
} from "./alert.service.js";

export async function evaluateUnattendedCustomerController(req, res) {
  try {
    const result = await evaluateUnattendedCustomer(
      req.user.organizationId,
      req.params.sessionId
    );
    return res.status(200).json({ success: true, data: result });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function getAlertsController(req, res) {
  try {
    const result = await getAlerts(req.user.organizationId, req.query);
    return res.status(200).json({
      success: true,
      data: result.alerts,
      pagination: result.pagination,
    });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getAlertByIdController(req, res) {
  try {
    const alert = await getAlertById(req.user.organizationId, req.params.id);
    return res.status(200).json({ success: true, data: alert });
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}

export async function acknowledgeAlertController(req, res) {
  try {
    const alert = await acknowledgeAlert(
      req.user.organizationId,
      req.params.id,
      req.user.userId
    );
    return res.status(200).json({
      success: true,
      message: "Alert acknowledged",
      data: alert,
    });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function resolveAlertController(req, res) {
  try {
    const alert = await resolveAlert(
      req.user.organizationId,
      req.params.id,
      req.user.userId,
      req.body.resolutionNotes
    );
    return res.status(200).json({
      success: true,
      message: "Alert resolved",
      data: alert,
    });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}
