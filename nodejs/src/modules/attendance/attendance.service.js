import prisma from "../../config/database.js";

const COOLDOWN_SECONDS = parseInt(process.env.ATTENDANCE_COOLDOWN_SECONDS || "60", 10);

export async function processAiAttendanceEvent(payload) {
  const { eventId, cameraId, employeeId, eventType, confidence, timestamp } = payload;
  const eventTimestamp = new Date(timestamp);

  const camera = await prisma.cameras.findFirst({
    where: { camera_code: cameraId, status: "ACTIVE" },
  });
  if (!camera) {
    const exists = await prisma.cameras.findFirst({ where: { camera_code: cameraId } });
    const reason = exists ? "CAMERA_INACTIVE" : "CAMERA_NOT_FOUND";
    console.log(`[AI_ATTENDANCE] camera=${cameraId} rejected reason=${reason}`);
    return { status: 404, body: { success: false, reason, message: reason === "CAMERA_NOT_FOUND" ? "Camera not found" : "Camera is not active" } };
  }

  const { organization_id: organizationId, store_id: storeId, id: cameraDbId } = camera;

  const employee = await prisma.employees.findFirst({
    where: { employee_code: employeeId, organization_id: organizationId },
  });
  if (!employee) {
    console.log(`[AI_ATTENDANCE] camera=${cameraId} employeeCode=${employeeId} reason=EMPLOYEE_NOT_FOUND`);
    return { status: 404, body: { success: false, reason: "EMPLOYEE_NOT_FOUND", message: "Employee not found" } };
  }
  if (employee.status !== "ACTIVE") {
    console.log(`[AI_ATTENDANCE] camera=${cameraId} employeeCode=${employeeId} reason=EMPLOYEE_INACTIVE`);
    return { status: 422, body: { success: false, reason: "EMPLOYEE_INACTIVE", message: "Employee is not active" } };
  }

  console.log(`[AI_ATTENDANCE] camera=${cameraId} employeeId=${employee.id} confidence=${confidence} event=${eventType}`);

  try {
    const result = await prisma.$transaction(async (tx) => {
      const existingEvent = await tx.ai_events.findFirst({
        where: { organization_id: organizationId, event_id: eventId },
      });
      if (existingEvent) {
        console.log(`[AI_ATTENDANCE] eventId=${eventId} reason=DUPLICATE_EVENT`);
        return { processed: false, reason: "DUPLICATE_EVENT" };
      }

      const cooldownFrom = new Date(eventTimestamp.getTime() - COOLDOWN_SECONDS * 1000);
      const recentEvent = await tx.ai_events.findFirst({
        where: {
          organization_id: organizationId,
          employee_id: employee.id,
          camera_id: cameraDbId,
          event_timestamp: { gte: cooldownFrom },
          processing_status: "PROCESSED",
        },
        orderBy: { event_timestamp: "desc" },
      });
      if (recentEvent) {
        console.log(`[AI_ATTENDANCE] employeeId=${employee.id} reason=COOLDOWN`);
        return { processed: false, reason: "COOLDOWN" };
      }

      const openSession = await tx.employee_sessions.findFirst({
        where: {
          employee_id: employee.id,
          organization_id: organizationId,
          status: "ACTIVE",
          session_end: null,
        },
        orderBy: { session_start: "desc" },
      });

      let attendanceAction;
      let session;

      if (!openSession) {
        session = await tx.employee_sessions.create({
          data: {
            organization_id: organizationId,
            employee_id: employee.id,
            store_id: storeId,
            session_start: eventTimestamp,
            session_end: null,
            status: "ACTIVE",
          },
        });
        attendanceAction = "IN";
        console.log(`[AI_ATTENDANCE] employeeId=${employee.id} action=IN sessionId=${session.id}`);
      } else {
        session = await tx.employee_sessions.update({
          where: { id: openSession.id },
          data: {
            session_end: eventTimestamp,
            status: "COMPLETED",
            updated_at: new Date(),
          },
        });
        attendanceAction = "OUT";
        console.log(`[AI_ATTENDANCE] employeeId=${employee.id} action=OUT sessionId=${session.id}`);
      }

      await tx.ai_events.create({
        data: {
          organization_id: organizationId,
          store_id: storeId,
          camera_id: cameraDbId,
          employee_id: employee.id,
          employee_session_id: session.id,
          event_id: eventId,
          event_type: eventType,
          confidence: confidence,
          event_timestamp: eventTimestamp,
          subject_id: employeeId,
          processing_status: "PROCESSED",
          raw_payload: payload,
          normalized_payload: {
            attendanceAction,
            employeeCode: employee.employee_code,
            cameraCode: cameraId,
            organizationId,
            storeId,
            sessionId: session.id,
          },
        },
      });

      return { processed: true, attendanceAction, session, openSession };
    });

    if (!result.processed) {
      return { status: 200, body: { success: true, processed: false, reason: result.reason } };
    }

    // ── Upsert employee_attendance table ──────────────────────────────────────
    try {
      // Use IST date for attendance_date
      const attendanceDate = eventTimestamp.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
      if (result.attendanceAction === "IN") {
        await prisma.$executeRaw`
          INSERT INTO employee_attendance
            (organization_id, store_id, employee_id, attendance_date, check_in, status, camera_code, confidence)
          VALUES
            (${organizationId}::uuid, ${storeId}::uuid, ${employee.id}::uuid,
             ${attendanceDate}::date, ${eventTimestamp}, 'Present',
             ${cameraId}, ${confidence})
          ON CONFLICT (organization_id, employee_id, attendance_date)
          DO UPDATE SET
            check_in   = EXCLUDED.check_in,
            status     = 'Present',
            updated_at = NOW()
        `;
      } else {
        const durationMin = result.openSession
          ? Math.round((eventTimestamp - new Date(result.openSession.session_start)) / 60000)
          : null;
        await prisma.$executeRaw`
          UPDATE employee_attendance
          SET check_out        = ${eventTimestamp},
              status           = 'Checked Out',
              duration_minutes = ${durationMin},
              updated_at       = NOW()
          WHERE organization_id = ${organizationId}::uuid
            AND employee_id     = ${employee.id}::uuid
            AND attendance_date = ${attendanceDate}::date
        `;
      }
    } catch (e) {
      console.error("[ATTENDANCE_TABLE] upsert failed:", e.message);
    }

    return {
      status: 200,
      body: {
        success: true,
        processed: true,
        attendanceAction: result.attendanceAction,
        employee: {
          id: employee.id,
          employeeCode: employee.employee_code,
          name: `${employee.first_name}${employee.last_name ? " " + employee.last_name : ""}`.trim(),
        },
        camera: { cameraCode: cameraId },
        sessionId: result.session.id,
        eventId,
      },
    };
  } catch (error) {
    if (error.code === "P2002") {
      console.log(`[AI_ATTENDANCE] eventId=${eventId} reason=DUPLICATE_EVENT (race)`);
      return { status: 200, body: { success: true, processed: false, reason: "DUPLICATE_EVENT" } };
    }
    console.error(`[AI_ATTENDANCE] transaction failed eventId=${eventId}`, error.message);
    throw error;
  }
}

// ── Report Helpers ────────────────────────────────────────────────────────────

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

function formatDuration(start, end) {
  if (!end) return "Active";
  const ms = new Date(end) - new Date(start);
  const h  = Math.floor(ms / 3600000);
  const m  = Math.floor((ms % 3600000) / 60000);
  return `${h}h ${m}m`;
}

function formatTime(dt) {
  if (!dt) return null;
  return new Date(dt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" });
}

// ── Attendance Report ─────────────────────────────────────────────────────────

export async function getAttendanceReport(organizationId, { startDate, endDate, date, storeId, employeeId, status }) {
  const { start, end } = getDateRange(date, startDate, endDate);

  const org    = await prisma.organizations.findFirst({ where: { id: organizationId } });
  const stores = await prisma.stores.findMany({ where: { organization_id: organizationId, ...(storeId && { id: storeId }) } });

  const employees = await prisma.employees.findMany({
    where: {
      organization_id: organizationId,
      ...(storeId    && { store_id: storeId }),
      ...(employeeId && { id: employeeId }),
    },
  });

  const sessions = await prisma.employee_sessions.findMany({
    where: {
      organization_id: organizationId,
      session_start: { gte: start, lte: end },
      ...(storeId    && { store_id: storeId }),
      ...(employeeId && { employee_id: employeeId }),
    },
    orderBy: { session_start: "asc" },
  });

  const sessionMap = {};
  for (const s of sessions) {
    if (!sessionMap[s.employee_id]) sessionMap[s.employee_id] = [];
    sessionMap[s.employee_id].push(s);
  }

  const records = employees.map((emp) => {
    const empSessions = sessionMap[emp.id] || [];
    const firstIn     = empSessions[0];
    const lastOut     = empSessions.filter(s => s.session_end).pop();
    const empStatus   = empSessions.length === 0 ? "Absent"
      : empSessions.some(s => s.status === "ACTIVE") ? "Present"
      : "Checked Out";

    if (status && status !== empStatus) return null;

    return {
      employeeId:   emp.id,
      employeeCode: emp.employee_code,
      name:         `${emp.first_name}${emp.last_name ? " " + emp.last_name : ""}`.trim(),
      checkIn:      firstIn ? formatTime(firstIn.session_start) : null,
      checkOut:     lastOut ? formatTime(lastOut.session_end)   : null,
      duration:     firstIn ? formatDuration(firstIn.session_start, lastOut?.session_end) : null,
      status:       empStatus,
      sessions:     empSessions.length,
    };
  }).filter(Boolean);

  return {
    organization:   { id: org.id, name: org.name },
    stores:         stores.map(s => ({ id: s.id, name: s.name, storeCode: s.store_code })),
    dateRange:      { start: start.toISOString(), end: end.toISOString() },
    totalEmployees: employees.length,
    records,
  };
}

// ── Summary ───────────────────────────────────────────────────────────────────

export async function getAttendanceSummary(organizationId, { date, storeId }) {
  const { start, end } = getDateRange(date, null, null);
  const org = await prisma.organizations.findFirst({ where: { id: organizationId } });

  const totalEmployees = await prisma.employees.count({
    where: { organization_id: organizationId, status: "ACTIVE", ...(storeId && { store_id: storeId }) },
  });

  const sessions = await prisma.employee_sessions.findMany({
    where: {
      organization_id: organizationId,
      session_start: { gte: start, lte: end },
      ...(storeId && { store_id: storeId }),
    },
    select: { employee_id: true, status: true },
  });

  const presentIds = new Set(sessions.map(s => s.employee_id));
  const onBreakIds = new Set(sessions.filter(s => s.status === "ACTIVE").map(s => s.employee_id));

  return {
    organization:   { id: org.id, name: org.name },
    date:           date || new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
    totalEmployees,
    present:        presentIds.size,
    onBreak:        onBreakIds.size,
    absent:         totalEmployees - presentIds.size,
    attendanceRate: totalEmployees > 0 ? Math.round((presentIds.size / totalEmployees) * 100) : 0,
  };
}

// ── Weekly Trend ──────────────────────────────────────────────────────────────

export async function getAttendanceTrend(organizationId, { storeId }) {
  const days   = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const today  = new Date();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  monday.setHours(0, 0, 0, 0);

  const trend = [];
  for (let i = 0; i < 7; i++) {
    const dayStart = new Date(monday); dayStart.setDate(monday.getDate() + i);
    const dayEnd   = new Date(dayStart); dayEnd.setHours(23, 59, 59, 999);

    const sessions = await prisma.employee_sessions.findMany({
      where: {
        organization_id: organizationId,
        session_start: { gte: dayStart, lte: dayEnd },
        ...(storeId && { store_id: storeId }),
      },
      select: { employee_id: true },
    });

    const totalEmployees = await prisma.employees.count({
      where: { organization_id: organizationId, status: "ACTIVE", ...(storeId && { store_id: storeId }) },
    });

    const present = new Set(sessions.map(s => s.employee_id)).size;
    trend.push({ day: days[i], date: dayStart.toISOString().slice(0, 10), present, absent: totalEmployees - present });
  }

  return { trend };
}

// ── Live Face Recognition Log ─────────────────────────────────────────────────

export async function getLiveLog(organizationId, { storeId, limit }) {
  const events = await prisma.ai_events.findMany({
    where: {
      organization_id: organizationId,
      event_type: "FACE_RECOGNIZED",
      processing_status: "PROCESSED",
      ...(storeId && { store_id: storeId }),
    },
    orderBy: { event_timestamp: "desc" },
    take: limit,
    include: {
      employees: { select: { first_name: true, last_name: true, employee_code: true } },
      cameras:   { select: { camera_code: true, name: true } },
    },
  });

  return events.map(e => ({
    employeeCode: e.employees?.employee_code,
    name:         e.employees ? `${e.employees.first_name}${e.employees.last_name ? " " + e.employees.last_name : ""}`.trim() : e.subject_id,
    camera:       e.cameras?.name || e.cameras?.camera_code,
    event:        e.normalized_payload?.attendanceAction === "IN" ? "Check-in" : "Check-out",
    confidence:   e.confidence ? `${(parseFloat(e.confidence) * 100).toFixed(1)}%` : null,
    timestamp:    e.event_timestamp,
    method:       "Face Recognition",
  }));
}
