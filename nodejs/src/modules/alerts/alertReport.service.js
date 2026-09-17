import prisma from "../../config/database.js";

function getDateRange(date, startDate, endDate) {
  if (date) {
    return {
      start: new Date(`${date}T00:00:00+05:30`),
      end:   new Date(`${date}T23:59:59+05:30`),
    };
  }
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  return {
    start: new Date(startDate ? `${startDate}T00:00:00+05:30` : `${today}T00:00:00+05:30`),
    end:   new Date(endDate   ? `${endDate}T23:59:59+05:30`   : `${today}T23:59:59+05:30`),
  };
}

function formatTime(dt) {
  if (!dt) return null;
  return new Date(dt).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata", day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

export async function getAlertReport(organizationId, { date, startDate, endDate, storeId, status, severity }) {
  const { start, end } = getDateRange(date, startDate, endDate);

  const org    = await prisma.organizations.findFirst({ where: { id: organizationId } });
  const stores = await prisma.stores.findMany({ where: { organization_id: organizationId, ...(storeId && { id: storeId }) } });

  const alerts = await prisma.alerts.findMany({
    where: {
      organization_id: organizationId,
      created_at: { gte: start, lte: end },
      ...(storeId  && { store_id: storeId }),
      ...(status   && { status }),
      ...(severity && { severity }),
    },
    orderBy: { created_at: "desc" },
    include: {
      customer_sessions: { select: { session_code: true } },
      business_rules:    { select: { name: true } },
    },
  });

  const total        = alerts.length;
  const open         = alerts.filter(a => a.status === "OPEN").length;
  const acknowledged = alerts.filter(a => a.status === "ACKNOWLEDGED").length;
  const resolved     = alerts.filter(a => a.status === "RESOLVED").length;
  const high         = alerts.filter(a => a.severity === "HIGH").length;

  const records = alerts.map((a, idx) => ({
    index:      idx + 1,
    alertCode:  a.alert_code,
    title:      a.title,
    severity:   a.severity,
    status:     a.status,
    session:    a.customer_sessions?.session_code || "--",
    rule:       a.business_rules?.name || "--",
    raisedAt:   formatTime(a.created_at),
    resolvedAt: formatTime(a.resolved_at),
  }));

  return {
    organization: { id: org.id, name: org.name },
    stores:       stores.map(s => ({ id: s.id, name: s.name })),
    dateRange:    { start: start.toISOString(), end: end.toISOString() },
    total, open, acknowledged, resolved, high,
    records,
  };
}
