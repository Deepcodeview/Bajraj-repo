"""
database/models.py — SQLAlchemy ORM models for persistent job storage.
"""

from sqlalchemy import Column, String, Float, Integer, JSON, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
import datetime
import enum

Base = declarative_base()


class JobStatus(str, enum.Enum):
    QUEUED      = "queued"
    PROCESSING  = "processing"
    COMPLETED   = "completed"
    FAILED      = "failed"


class AnalyticsJob(Base):
    __tablename__ = "analytics_jobs"

    job_id          = Column(String, primary_key=True, index=True)
    filename        = Column(String, nullable=False)
    status          = Column(String, default=JobStatus.QUEUED)
    progress        = Column(Integer, default=0)
    error_message   = Column(String, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at    = Column(DateTime, nullable=True)
    result          = Column(JSON, nullable=True)


class CrossingEvent(Base):
    __tablename__ = "crossing_events"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    job_id          = Column(String, index=True)
    global_id       = Column(Integer)
    event_type      = Column(String)
    timestamp_sec   = Column(Float)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    job_id          = Column(String, index=True)
    severity        = Column(String)
    message         = Column(String)
    timestamp_sec   = Column(Float)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── POS Transactions (manual entry or API sync) ───────────────────────────────
class POSTransaction(Base):
    __tablename__ = "pos_transactions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    bill_number     = Column(String, nullable=True)
    amount          = Column(Float, default=0.0)
    items_count     = Column(Integer, default=1)
    zone            = Column(String, nullable=True)   # which zone customer came from
    transaction_at  = Column(DateTime, default=datetime.datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Shelf Events (empty/low/restocked) ────────────────────────────────────────
class ShelfEvent(Base):
    __tablename__ = "shelf_events"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    job_id          = Column(String, index=True, nullable=True)
    store_id        = Column(String, index=True, default="store_1")
    zone            = Column(String, nullable=True)
    event_type      = Column(String)   # EMPTY | LOW_STOCK | RESTOCKED
    duration_min    = Column(Float, nullable=True)   # how long shelf was empty
    timestamp_sec   = Column(Float, nullable=True)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at     = Column(DateTime, nullable=True)


# ── Promotions ────────────────────────────────────────────────────────────────
class Promotion(Base):
    __tablename__ = "promotions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    name            = Column(String)
    zone            = Column(String, nullable=True)
    discount_pct    = Column(Float, default=0.0)
    start_date      = Column(DateTime)
    end_date        = Column(DateTime)
    pre_footfall    = Column(Integer, nullable=True)   # footfall before promo
    post_footfall   = Column(Integer, nullable=True)   # footfall during promo
    pre_dwell_min   = Column(Float, nullable=True)
    post_dwell_min  = Column(Float, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Stores (multi-store enterprise) ──────────────────────────────────────────
class Store(Base):
    __tablename__ = "stores"

    id              = Column(String, primary_key=True)   # "store_1", "store_2"
    name            = Column(String)
    location        = Column(String, nullable=True)
    manager_email   = Column(String, nullable=True)
    manager_phone   = Column(String, nullable=True)
    whatsapp_number = Column(String, nullable=True)
    active          = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Integration Config ────────────────────────────────────────────────────────
class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    integration     = Column(String)   # whatsapp | pos | erp | slack | email
    enabled         = Column(Boolean, default=False)
    config_json     = Column(JSON, nullable=True)   # {api_key, endpoint, phone, ...}
    last_triggered  = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Anomaly Log (auto-detected unusual patterns) ──────────────────────────────
class AnomalyLog(Base):
    __tablename__ = "anomaly_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    anomaly_type    = Column(String)   # crowd_spike | camera_offline | long_dwell | low_traffic
    zone            = Column(String, nullable=True)
    value           = Column(Float, nullable=True)   # actual observed value
    baseline        = Column(Float, nullable=True)   # expected baseline
    deviation_pct   = Column(Float, nullable=True)
    severity        = Column(String, default="MEDIUM")  # LOW | MEDIUM | HIGH | CRITICAL
    message         = Column(Text, nullable=True)
    resolved        = Column(Boolean, default=False)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── Occupancy Events (capacity tracking) ─────────────────────────────────────
class OccupancyEvent(Base):
    __tablename__ = "occupancy_events"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    zone            = Column(String, nullable=True)
    count           = Column(Integer, default=0)
    max_capacity    = Column(Integer, default=50)
    breached        = Column(Boolean, default=False)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── Staff Zone Log (staff activity tracking) ──────────────────────────────────
class StaffZoneLog(Base):
    __tablename__ = "staff_zone_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    staff_id        = Column(String)
    zone            = Column(String)
    duration_min    = Column(Float, default=0.0)
    shift_date      = Column(DateTime, default=datetime.datetime.utcnow)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── Feedback Entry (kiosk / exit survey) ─────────────────────────────────────
class FeedbackEntry(Base):
    __tablename__ = "feedback_entries"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    zone            = Column(String, nullable=True)   # last zone visited before exit
    rating          = Column(Integer)                 # 1–5
    comment         = Column(Text, nullable=True)
    customer_id     = Column(String, nullable=True)   # loyalty ID if opt-in
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── Custom Report (user-defined metric selection) ─────────────────────────────
class CustomReport(Base):
    __tablename__ = "custom_reports"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    name            = Column(String)
    metrics         = Column(JSON)        # list of selected metric keys
    filters         = Column(JSON, nullable=True)   # date range, zones, etc.
    created_by      = Column(String, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Scheduled Report ──────────────────────────────────────────────────────────
class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    name            = Column(String)
    frequency       = Column(String)      # daily | weekly | monthly
    format          = Column(String, default="pdf")   # pdf | excel | both
    recipients      = Column(JSON)        # list of email addresses
    metrics         = Column(JSON, nullable=True)
    enabled         = Column(Boolean, default=True)
    last_sent       = Column(DateTime, nullable=True)
    next_run        = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Whitelabel Config ─────────────────────────────────────────────────────────
class WhitelabelConfig(Base):
    __tablename__ = "whitelabel_configs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    client_id       = Column(String, unique=True, index=True)
    brand_name      = Column(String, default="RetailVision")
    logo_url        = Column(String, nullable=True)
    primary_color   = Column(String, default="#0057ff")
    accent_color    = Column(String, default="#7c3aed")
    custom_domain   = Column(String, nullable=True)
    support_email   = Column(String, nullable=True)
    language        = Column(String, default="en")   # en | hi | mr
    active          = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── API Key (third-party integration) ────────────────────────────────────────
class APIKey(Base):
    __tablename__ = "api_keys"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    key_name        = Column(String)
    key_hash        = Column(String, unique=True)   # hashed API key
    key_prefix      = Column(String)                # first 8 chars for display
    scopes          = Column(JSON, default=list)    # ["read", "write", "alerts"]
    active          = Column(Boolean, default=True)
    last_used       = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)


# ── Person Movement Log (cross-camera tracking) ─────────────────────────────
class PersonMovementLog(Base):
    __tablename__ = "person_movement_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    global_id   = Column(Integer, index=True)          # stable cross-camera ID
    camera_id   = Column(String, index=True)           # "cam1", "cam2", etc.
    camera_name = Column(String, nullable=True)        # "Entrance / Main Gate"
    event_type  = Column(String)                       # "appeared" | "disappeared"
    zone        = Column(String, nullable=True)        # grid zone at time of event
    bbox_x1     = Column(Integer, nullable=True)
    bbox_y1     = Column(Integer, nullable=True)
    bbox_x2     = Column(Integer, nullable=True)
    bbox_y2     = Column(Integer, nullable=True)
    wall_time   = Column(DateTime, default=datetime.datetime.utcnow)
    store_id    = Column(String, index=True, default="store_1")


# ── Attendance Log (face recognition) ───────────────────────────────────────
class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    name            = Column(String, index=True)
    type            = Column(String, default="employee")
    attendance_date = Column(String, index=True)
    first_seen_time = Column(DateTime)
    similarity      = Column(Float, nullable=True)
    camera_id       = Column(String, nullable=True)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── Customer Journey Log ────────────────────────────────────────────────────────────
class CustomerJourney(Base):
    __tablename__ = "customer_journeys"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    store_id    = Column(String, index=True, default="store_1")
    global_id   = Column(Integer, index=True)
    journey     = Column(JSON)        # [{zone, camera_id, entered_at, exited_at, dwell_sec}]
    total_dwell_sec = Column(Float, default=0.0)
    zones_visited   = Column(Integer, default=0)
    entry_time  = Column(DateTime, nullable=True)
    exit_time   = Column(DateTime, nullable=True)
    is_repeat   = Column(Boolean, default=False)   # repeat visitor
    wall_time   = Column(DateTime, default=datetime.datetime.utcnow)


# ── Loitering Alert ───────────────────────────────────────────────────────────────────
class LoiteringAlert(Base):
    __tablename__ = "loitering_alerts"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    store_id    = Column(String, index=True, default="store_1")
    global_id   = Column(Integer, index=True)
    camera_id   = Column(String)
    zone        = Column(String, nullable=True)
    dwell_sec   = Column(Float)
    resolved    = Column(Boolean, default=False)
    wall_time   = Column(DateTime, default=datetime.datetime.utcnow)


# ── Shelf Interaction Log ───────────────────────────────────────────────────────────
class ShelfInteractionLog(Base):
    __tablename__ = "shelf_interaction_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    global_id       = Column(Integer, index=True)
    camera_id       = Column(String)
    zone            = Column(String, nullable=True)
    interaction     = Column(String)   # pickup | replace | browse
    dwell_sec       = Column(Float, default=0.0)
    wall_time       = Column(DateTime, default=datetime.datetime.utcnow)


# ── Real-time Alert Engine Log ─────────────────────────────────────────────────────
class AlertEngineLog(Base):
    __tablename__ = "alert_engine_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    store_id    = Column(String, index=True, default="store_1")
    alert_type  = Column(String, index=True)
    severity    = Column(String, default="MEDIUM")
    camera_id   = Column(String, nullable=True)
    zone        = Column(String, nullable=True)
    global_id   = Column(Integer, nullable=True)
    message     = Column(Text)
    extra_data  = Column(JSON, nullable=True)   # renamed from metadata
    resolved    = Column(Boolean, default=False)
    wall_time   = Column(DateTime, default=datetime.datetime.utcnow)


# ── Footfall Log (people count snapshots) ───────────────────────────────────
class FootfallLog(Base):
    __tablename__ = "footfall_logs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    store_id         = Column(String, index=True, default="store_1")
    camera_id        = Column(String, index=True)
    log_date         = Column(String, index=True)   # "YYYY-MM-DD" IST
    entries          = Column(Integer, default=0)   # cumulative entries since stream start
    exits            = Column(Integer, default=0)
    currently_inside = Column(Integer, default=0)
    total_unique     = Column(Integer, default=0)
    wall_time        = Column(DateTime, default=datetime.datetime.utcnow)


# ── Edge Device Config ────────────────────────────────────────────────────────
class EdgeDevice(Base):
    __tablename__ = "edge_devices"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    store_id        = Column(String, index=True, default="store_1")
    device_id       = Column(String, unique=True)
    device_type     = Column(String)    # jetson_nano | jetson_orin | oak_d | raspberry_pi
    ip_address      = Column(String, nullable=True)
    night_mode      = Column(Boolean, default=False)
    night_threshold = Column(Integer, default=60)   # brightness 0-255
    model_variant   = Column(String, default="yolov8n")  # yolov8n | yolov8s
    status          = Column(String, default="offline")  # online | offline | error
    last_heartbeat  = Column(DateTime, nullable=True)
    config_json     = Column(JSON, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)