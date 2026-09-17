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
  return new Date(dt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" });
}

function formatDuration(start, end) {
  if (!end) return "Active";
  const ms = new Date(end) - new Date(start);
  const h  = Math.floor(ms / 3600000);
  const m  = Math.floor((ms % 3600000) / 60000);
  return `${h}h ${m}m`;
}

export async function getCustomerReport(organizationId, { date, startDate, endDate, storeId }) {
  const { start, end } = getDateRange(date, startDate, endDate);

  const org    = await prisma.organizations.findFirst({ where: { id: organizationId } });
  const stores = await prisma.stores.findMany({ where: { organization_id: organizationId, ...(storeId && { id: storeId }) } });

  const sessions = await prisma.customer_sessions.findMany({
    where: {
      organization_id: organizationId,
      start_time: { gte: start, lte: end },
      ...(storeId && { store_id: storeId }),
    },
    orderBy: { start_time: "asc" },
    include: {
      zones:     { select: { name: true } },
      employees: { select: { first_name: true, last_name: true, employee_code: true } },
    },
  });

  const records = sessions.map((s, idx) => ({
    index:        idx + 1,
    sessionCode:  s.session_code,
    entryTime:    formatTime(s.start_time),
    exitTime:     formatTime(s.end_time),
    duration:     formatDuration(s.start_time, s.end_time),
    zone:         s.zones?.name || "--",
    assignedTo:   s.employees ? `${s.employees.first_name}${s.employees.last_name ? " " + s.employees.last_name : ""}`.trim() : "--",
    status:       s.status,
  }));

  const totalVisitors = records.length;
  const active        = records.filter(r => r.status === "ACTIVE").length;
  const completed     = records.filter(r => r.status === "COMPLETED").length;

  const completedMs = sessions
    .filter(s => s.end_time)
    .map(s => new Date(s.end_time) - new Date(s.start_time));
  const avgDuration = completedMs.length
    ? Math.round(completedMs.reduce((a, b) => a + b, 0) / completedMs.length / 60000)
    : 0;

  return {
    organization:  { id: org.id, name: org.name },
    stores:        stores.map(s => ({ id: s.id, name: s.name })),
    dateRange:     { start: start.toISOString(), end: end.toISOString() },
    totalVisitors,
    active,
    completed,
    avgDurationMin: avgDuration,
    records,
  };
}

export async function getCustomerSummary(organizationId, { date, storeId }) {
  const { start, end } = getDateRange(date, null, null);
  const org = await prisma.organizations.findFirst({ where: { id: organizationId } });

  const sessions = await prisma.customer_sessions.findMany({
    where: {
      organization_id: organizationId,
      start_time: { gte: start, lte: end },
      ...(storeId && { store_id: storeId }),
    },
    select: { status: true, start_time: true, end_time: true },
  });

  const active    = sessions.filter(s => s.status === "ACTIVE").length;
  const completed = sessions.filter(s => s.status === "COMPLETED").length;

  const completedMs = sessions
    .filter(s => s.end_time)
    .map(s => new Date(s.end_time) - new Date(s.start_time));
  const avgDuration = completedMs.length
    ? Math.round(completedMs.reduce((a, b) => a + b, 0) / completedMs.length / 60000)
    : 0;

  return {
    organization:   { id: org.id, name: org.name },
    date:           date || new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
    totalVisitors:  sessions.length,
    active,
    completed,
    avgDurationMin: avgDuration,
  };
}
