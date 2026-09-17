-- Run this in pgAdmin Query Tool

CREATE TABLE IF NOT EXISTS employee_attendance (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  store_id          UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  employee_id       UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  attendance_date   DATE NOT NULL,
  check_in          TIMESTAMPTZ,
  check_out         TIMESTAMPTZ,
  duration_minutes  INTEGER,
  status            VARCHAR(20) NOT NULL DEFAULT 'Absent',
  camera_code       VARCHAR(100),
  confidence        DECIMAL(5,4),
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_employee_attendance_date
    UNIQUE (organization_id, employee_id, attendance_date)
);

CREATE INDEX IF NOT EXISTS idx_emp_attendance_org      ON employee_attendance(organization_id);
CREATE INDEX IF NOT EXISTS idx_emp_attendance_employee ON employee_attendance(employee_id);
CREATE INDEX IF NOT EXISTS idx_emp_attendance_date     ON employee_attendance(attendance_date);
CREATE INDEX IF NOT EXISTS idx_emp_attendance_store    ON employee_attendance(store_id);
