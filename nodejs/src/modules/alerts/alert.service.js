import prisma from "../../config/database.js";

function generateAlertCode() {
  const random = Math.random().toString(36).substring(2, 8).toUpperCase();
  return `ALT-${Date.now()}-${random}`;
}

// ── Core rule evaluation ──────────────────────────────────────────
// This does NOT care who calls it. Could be a manual test endpoint
// today, a webhook the AI service hits tomorrow, or a cron job that
// polls active sessions later. Trigger mechanism is a separate
// decision from this logic.
export async function evaluateUnattendedCustomer(organizationId, sessionId) {
  const session = await prisma.customer_sessions.findFirst({
    where: { id: sessionId, organization_id: organizationId },
  });

  if (!session) {
    throw new Error("Customer session not found");
  }

  if (session.status !== "ACTIVE") {
    return { breached: false, reason: "Session is not active" };
  }

  if (session.assigned_employee_id) {
    return { breached: false, reason: "Customer already engaged by an employee" };
  }

  // Find an active UNATTENDED_CUSTOMER rule for this store (zone-specific
  // rule wins over a store-wide one if both exist).
  const rule = await prisma.business_rules.findFirst({
    where: {
      organization_id: organizationId,
      store_id: session.store_id,
      rule_type: "UNATTENDED_CUSTOMER",
      is_active: true,
      OR: [
        { zone_id: session.current_zone_id },
        { zone_id: null },
      ],
    },
    orderBy: {
      zone_id: "desc", // non-null (zone-specific) rules sort first
    },
  });

  if (!rule) {
    return { breached: false, reason: "No active unattended-customer rule configured for this store/zone" };
  }

  const thresholdSeconds = rule.threshold_config?.thresholdSeconds;
  if (!thresholdSeconds) {
    return { breached: false, reason: "Rule has no thresholdSeconds configured" };
  }

  const elapsedSeconds = (Date.now() - new Date(session.start_time).getTime()) / 1000;

  if (elapsedSeconds < thresholdSeconds) {
    return {
      breached: false,
      reason: "Threshold not yet exceeded",
      elapsedSeconds: Math.round(elapsedSeconds),
      thresholdSeconds,
    };
  }

  // Avoid creating duplicate OPEN alerts for the same session + rule
  const existingAlert = await prisma.alerts.findFirst({
    where: {
      customer_session_id: sessionId,
      business_rule_id: rule.id,
      status: "OPEN",
    },
  });

  if (existingAlert) {
    return { breached: true, alert: existingAlert, alreadyExisted: true };
  }

  const zone = session.current_zone_id
    ? await prisma.zones.findUnique({ where: { id: session.current_zone_id } })
    : null;

  const alert = await prisma.alerts.create({
    data: {
      organization_id: organizationId,
      store_id: session.store_id,
      alert_code: generateAlertCode(),
      customer_session_id: sessionId,
      business_rule_id: rule.id,
      severity: rule.severity || "MEDIUM",
      title: "Unattended Customer",
      description: `Customer unattended for ${Math.round(elapsedSeconds)}s in ${
        zone ? zone.name : "an unspecified zone"
      } (threshold: ${thresholdSeconds}s).`,
      status: "OPEN",
    },
  });

  return { breached: true, alert, alreadyExisted: false };
}

// ── Standard alert CRUD ────────────────────────────────────────────
export async function getAlerts(organizationId, filters = {}) {
  const { storeId, status, severity, page = 1, limit = 20 } = filters;

  const where = { organization_id: organizationId };
  if (storeId) where.store_id = storeId;
  if (status) where.status = status;
  if (severity) where.severity = severity;

  const skip = (Number(page) - 1) * Number(limit);

  const [alerts, total] = await Promise.all([
    prisma.alerts.findMany({
      where,
      orderBy: { created_at: "desc" },
      skip,
      take: Number(limit),
    }),
    prisma.alerts.count({ where }),
  ]);

  return {
    alerts,
    pagination: {
      page: Number(page),
      limit: Number(limit),
      total,
      totalPages: Math.ceil(total / Number(limit)),
    },
  };
}

export async function getAlertById(organizationId, alertId) {
  const alert = await prisma.alerts.findFirst({
    where: { id: alertId, organization_id: organizationId },
    include: {
      customer_sessions: true,
      business_rules: true,
      evidence: true,
    },
  });

  if (!alert) {
    throw new Error("Alert not found");
  }

  return alert;
}

export async function acknowledgeAlert(organizationId, alertId, userId) {
  const alert = await prisma.alerts.findFirst({
    where: { id: alertId, organization_id: organizationId },
  });

  if (!alert) {
    throw new Error("Alert not found");
  }

  return prisma.alerts.update({
    where: { id: alertId },
    data: {
      status: "ACKNOWLEDGED",
      acknowledged_by: userId,
      acknowledged_at: new Date(),
    },
  });
}

export async function resolveAlert(organizationId, alertId, userId, resolutionNotes) {
  const alert = await prisma.alerts.findFirst({
    where: { id: alertId, organization_id: organizationId },
  });

  if (!alert) {
    throw new Error("Alert not found");
  }

  return prisma.alerts.update({
    where: { id: alertId },
    data: {
      status: "RESOLVED",
      resolved_by: userId,
      resolved_at: new Date(),
      resolution_notes: resolutionNotes || null,
    },
  });
}
