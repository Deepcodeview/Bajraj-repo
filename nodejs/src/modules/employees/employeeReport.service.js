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

function formatDuration(ms) {
  if (!ms || ms <= 0) return "0h 0m";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return `${h}h ${m}m`;
}

export async function getEmployeePerformanceReport(organizationId, { date, startDate, endDate, storeId }) {
  const { start, end } = getDateRange(date, startDate, endDate);

  const org    = await prisma.organizations.findFirst({ where: { id: organizationId } });
  const stores = await prisma.stores.findMany({ where: { organization_id: organizationId, ...(storeId && { id: storeId }) } });

  const employees = await prisma.employees.findMany({
    where: { organization_id: organizationId, status: "ACTIVE", ...(storeId && { store_id: storeId }) },
  });

  const sessions = await prisma.employee_sessions.findMany({
    where: {
      organization_id: organizationId,
      session_start: { gte: start, lte: end },
      ...(storeId && { store_id: storeId }),
    },
  });

  const customerSessions = await prisma.customer_sessions.findMany({
    where: {
      organization_id: organizationId,
      start_time: { gte: start, lte: end },
      assigned_employee_id: { not: null },
      ...(storeId && { store_id: storeId }),
    },
    select: {
      assigned_employee_id: true,
      response_time_seconds: true,
      start_time: true,
      end_time: true,
    },
  });

  const records = employees.map((emp, idx) => {
    const empSessions    = sessions.filter(s => s.employee_id === emp.id);
    const empCustomers   = customerSessions.filter(c => c.assigned_employee_id === emp.id);

    const totalWorkMs = empSessions
      .filter(s => s.session_end)
      .reduce((sum, s) => sum + (new Date(s.session_end) - new Date(s.session_start)), 0);

    const responseTimes  = empCustomers.map(c => c.response_time_seconds).filter(Boolean);
    const avgResponseSec = responseTimes.length
      ? Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length)
      : null;

    return {
      index:          idx + 1,
      employeeCode:   emp.employee_code,
      name:           `${emp.first_name}${emp.last_name ? " " + emp.last_name : ""}`.trim(),
      hoursWorked:    formatDuration(totalWorkMs),
      customersServed: empCustomers.length,
      avgResponseSec: avgResponseSec ? `${avgResponseSec}s` : "--",
      sessions:       empSessions.length,
      status:         empSessions.some(s => s.status === "ACTIVE") ? "Present" : empSessions.length > 0 ? "Checked Out" : "Absent",
    };
  });

  const totalPresent  = records.filter(r => r.status !== "Absent").length;
  const totalCustomers = records.reduce((sum, r) => sum + r.customersServed, 0);
  const allResponse   = customerSessions.map(c => c.response_time_seconds).filter(Boolean);
  const avgResponse   = allResponse.length
    ? Math.round(allResponse.reduce((a, b) => a + b, 0) / allResponse.length)
    : 0;

  return {
    organization:    { id: org.id, name: org.name },
    stores:          stores.map(s => ({ id: s.id, name: s.name })),
    dateRange:       { start: start.toISOString(), end: end.toISOString() },
    totalEmployees:  employees.length,
    totalPresent,
    totalCustomers,
    avgResponseSec:  avgResponse,
    records,
  };
}
