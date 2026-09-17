import {
  createCustomerSession,
  getCustomerSessions,
  getCustomerSessionById,
  assignEmployeeToSession,
  updateSessionZone,
  endCustomerSession,
  getCustomerCount,
} from "./customerSession.service.js";

export async function createCustomerSessionController(req, res) {
  try {
    const session = await createCustomerSession(
      req.user.organizationId,
      req.body
    );

    return res.status(201).json({
      success: true,
      message: "Customer session created successfully",
      data: session,
    });
  } catch (error) {
    return res.status(400).json({
      success: false,
      message: error.message,
    });
  }
}

export async function getCustomerSessionsController(req, res) {
  try {
    const result = await getCustomerSessions(
      req.user.organizationId,
      req.query
    );

    return res.status(200).json({
      success: true,
      data: result.sessions,
      pagination: result.pagination,
    });
  } catch (error) {
    return res.status(500).json({
      success: false,
      message: error.message,
    });
  }
}

export async function getCustomerSessionByIdController(req, res) {
  try {
    const session = await getCustomerSessionById(
      req.user.organizationId,
      req.params.id
    );

    return res.status(200).json({
      success: true,
      data: session,
    });
  } catch (error) {
    return res.status(404).json({
      success: false,
      message: error.message,
    });
  }
}

export async function assignEmployeeController(req, res) {
  try {
    const session = await assignEmployeeToSession(
      req.user.organizationId,
      req.params.id,
      req.body.employeeId
    );

    return res.status(200).json({
      success: true,
      message: "Employee assigned to session",
      data: session,
    });
  } catch (error) {
    return res.status(400).json({
      success: false,
      message: error.message,
    });
  }
}

export async function updateSessionZoneController(req, res) {
  try {
    const session = await updateSessionZone(
      req.user.organizationId,
      req.params.id,
      req.body.zoneId
    );

    return res.status(200).json({
      success: true,
      message: "Session zone updated",
      data: session,
    });
  } catch (error) {
    return res.status(400).json({
      success: false,
      message: error.message,
    });
  }
}

export async function endCustomerSessionController(req, res) {
  try {
    const session = await endCustomerSession(
      req.user.organizationId,
      req.params.id,
      req.body.status
    );

    return res.status(200).json({
      success: true,
      message: "Customer session closed",
      data: session,
    });
  } catch (error) {
    return res.status(400).json({
      success: false,
      message: error.message,
    });
  }
}

export async function getCustomerCountController(req, res) {
  try {
    const { storeId } = req.query;
    const data = await getCustomerCount(req.user.organizationId, storeId);
    return res.status(200).json({ success: true, data });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}
