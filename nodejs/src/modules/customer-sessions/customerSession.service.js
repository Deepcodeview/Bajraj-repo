import prisma from "../../config/database.js";

function generateSessionCode() {
  const random = Math.random().toString(36).substring(2, 8).toUpperCase();
  return `CS-${Date.now()}-${random}`;
}

export async function createCustomerSession(organizationId, data) {
  const store = await prisma.stores.findFirst({
    where: {
      id: data.storeId,
      organization_id: organizationId,
    },
  });

  if (!store) {
    throw new Error("Store not found for this organization");
  }

  if (data.zoneId) {
    const zone = await prisma.zones.findFirst({
      where: {
        id: data.zoneId,
        store_id: data.storeId,
      },
    });

    if (!zone) {
      throw new Error("Zone not found for this store");
    }
  }

  const session = await prisma.customer_sessions.create({
    data: {
      organization_id: organizationId,
      store_id: data.storeId,
      session_code: generateSessionCode(),
      customer_tracking_id: data.customerTrackingId || null,
      current_zone_id: data.zoneId || null,
      assigned_employee_id: data.employeeId || null,
      status: "ACTIVE",
    },
  });

  return session;
}

export async function getCustomerSessions(organizationId, filters = {}) {
  const { storeId, status, page = 1, limit = 20 } = filters;

  const where = {
    organization_id: organizationId,
  };

  if (storeId) {
    where.store_id = storeId;
  }

  if (status) {
    where.status = status;
  }

  const skip = (Number(page) - 1) * Number(limit);

  const [sessions, total] = await Promise.all([
    prisma.customer_sessions.findMany({
      where,
      orderBy: {
        start_time: "desc",
      },
      skip,
      take: Number(limit),
    }),
    prisma.customer_sessions.count({ where }),
  ]);

  return {
    sessions,
    pagination: {
      page: Number(page),
      limit: Number(limit),
      total,
      totalPages: Math.ceil(total / Number(limit)),
    },
  };
}

export async function getCustomerSessionById(organizationId, sessionId) {
  const session = await prisma.customer_sessions.findFirst({
    where: {
      id: sessionId,
      organization_id: organizationId,
    },
    include: {
      employees: true,
      zones: true,
      stores: true,
    },
  });

  if (!session) {
    throw new Error("Customer session not found");
  }

  return session;
}

// Assigns an employee to the session. If this is the FIRST time an employee
// is being assigned, this is the "first meaningful engagement" moment —
// we compute and store response_time_seconds (Module 2 requirement).
export async function assignEmployeeToSession(organizationId, sessionId, employeeId) {
  const session = await prisma.customer_sessions.findFirst({
    where: {
      id: sessionId,
      organization_id: organizationId,
    },
  });

  if (!session) {
    throw new Error("Customer session not found");
  }

  const employee = await prisma.employees.findFirst({
    where: {
      id: employeeId,
      organization_id: organizationId,
      store_id: session.store_id,
    },
  });

  if (!employee) {
    throw new Error("Employee not found for this store");
  }

  const isFirstEngagement = !session.assigned_employee_id;
  const updateData = {
    assigned_employee_id: employeeId,
  };

  if (isFirstEngagement) {
    const responseTimeSeconds =
      (Date.now() - new Date(session.start_time).getTime()) / 1000;
    updateData.response_time_seconds = responseTimeSeconds;
  }

  const updated = await prisma.customer_sessions.update({
    where: { id: sessionId },
    data: updateData,
  });

  return updated;
}

export async function updateSessionZone(organizationId, sessionId, zoneId) {
  const session = await prisma.customer_sessions.findFirst({
    where: {
      id: sessionId,
      organization_id: organizationId,
    },
  });

  if (!session) {
    throw new Error("Customer session not found");
  }

  const zone = await prisma.zones.findFirst({
    where: {
      id: zoneId,
      store_id: session.store_id,
    },
  });

  if (!zone) {
    throw new Error("Zone not found for this store");
  }

  const updated = await prisma.customer_sessions.update({
    where: { id: sessionId },
    data: { current_zone_id: zoneId },
  });

  return updated;
}

export async function endCustomerSession(organizationId, sessionId, status = "COMPLETED") {
  const session = await prisma.customer_sessions.findFirst({
    where: {
      id: sessionId,
      organization_id: organizationId,
    },
  });

  if (!session) {
    throw new Error("Customer session not found");
  }

  if (session.status !== "ACTIVE") {
    throw new Error("Session is already closed");
  }

  const updated = await prisma.customer_sessions.update({
    where: { id: sessionId },
    data: {
      end_time: new Date(),
      status,
    },
  });

  return updated;
}

// ── Customer Count ────────────────────────────────────────────────────────────
export async function getCustomerCount(organizationId, storeId) {
  const where = {
    organization_id: organizationId,
    status: "ACTIVE",
  };

  if (storeId) where.store_id = storeId;

  const activeSessions = await prisma.customer_sessions.findMany({
    where,
    include: {
      stores: { select: { id: true, name: true } },
      zones:  { select: { id: true, name: true } },
    },
    orderBy: { start_time: "asc" },
  });

  const storeBreakdown = {};
  for (const s of activeSessions) {
    const sid   = s.stores?.id   || s.store_id;
    const sname = s.stores?.name || "Unknown Store";
    if (!storeBreakdown[sid]) {
      storeBreakdown[sid] = { storeId: sid, storeName: sname, count: 0 };
    }
    storeBreakdown[sid].count += 1;
  }

  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);

  const todayTotal = await prisma.customer_sessions.count({
    where: {
      organization_id: organizationId,
      ...(storeId && { store_id: storeId }),
      start_time: { gte: todayStart },
    },
  });

  const todayCompleted = await prisma.customer_sessions.count({
    where: {
      organization_id: organizationId,
      ...(storeId && { store_id: storeId }),
      start_time: { gte: todayStart },
      status: "COMPLETED",
    },
  });

  return {
    currentlyInStore:   activeSessions.length,
    todayTotalVisitors: todayTotal,
    todayCompleted,
    storeBreakdown:     Object.values(storeBreakdown),
    asOf:               new Date().toISOString(),
  };
}
