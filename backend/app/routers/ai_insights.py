"""
routers/ai_insights.py — Predictive AI & Advanced Analytics for Retail AI

GET  /ai/footfall-forecast      → predict next 7 days footfall (linear trend + seasonality)
GET  /ai/demand-forecast        → predict reorder dates per zone from shelf-empty patterns
GET  /ai/anomalies              → list auto-detected anomalies
POST /ai/anomalies/scan         → trigger anomaly scan on latest data
GET  /ai/camera-health          → camera health status (offline / blurred / tampered)
POST /ai/camera-health/report   → report a camera issue
"""
import datetime
import math
import statistics
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import (
    AnalyticsJob, JobStatus, CrossingEvent, AlertLog,
    ShelfEvent, AnomalyLog,
)

router = APIRouter(prefix="/ai", tags=["ai_insights"])

# ── In-memory camera health registry ─────────────────────────────────────────
_camera_issues: list[dict] = []

SEASONS = {
    1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Summer",
    6: "Summer", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon", 10: "Autumn",
    11: "Autumn", 12: "Winter",
}
FESTIVALS = {
    10: "Navratri/Dussehra", 11: "Diwali", 12: "Christmas/New Year",
    8: "Independence Day", 1: "Republic Day / Makar Sankranti",
}
DOW_MULTIPLIER = [0.85, 0.88, 0.90, 0.92, 1.05, 1.25, 1.20]  # Mon–Sun


def _completed_jobs(db: Session):
    return (
        db.query(AnalyticsJob)
        .filter(AnalyticsJob.status == JobStatus.COMPLETED)
        .order_by(AnalyticsJob.completed_at)
        .all()
    )


# ── Footfall Forecast ─────────────────────────────────────────────────────────

@router.get("/footfall-forecast")
def footfall_forecast(days_ahead: int = 7, db: Session = Depends(get_db)):
    """
    Predict next N days footfall using:
    - Linear regression on last 30 days of data
    - Day-of-week multiplier
    - Festival/season boost
    """
    jobs = _completed_jobs(db)

    # Build daily series
    daily: dict[str, int] = defaultdict(int)
    for j in jobs:
        if j.completed_at and j.result:
            day = j.completed_at.strftime("%Y-%m-%d")
            daily[day] += (j.result or {}).get("entries", 0)

    today = datetime.date.today()
    series = []
    for i in range(29, -1, -1):
        d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        series.append(daily.get(d, 0))

    # Simple linear regression on last 30 days
    n = len(series)
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(series) if series else 0
    if y_mean == 0:
        # No data — return illustrative forecast
        base = 120
    else:
        numerator   = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n)) or 1
        slope       = numerator / denominator
        base        = y_mean + slope * (n / 2)

    # Forecast
    forecast = []
    for i in range(1, days_ahead + 1):
        future_date = today + datetime.timedelta(days=i)
        dow         = future_date.weekday()
        month       = future_date.month
        season      = SEASONS.get(month, "Normal")
        festival    = FESTIVALS.get(month)

        # Trend + DOW + festival boost
        trend_val   = max(0, base + slope * i if y_mean > 0 else base)
        dow_adj     = trend_val * DOW_MULTIPLIER[dow]
        fest_boost  = 1.15 if festival else 1.0
        predicted   = round(dow_adj * fest_boost)

        # Confidence interval ±15%
        ci_low  = round(predicted * 0.85)
        ci_high = round(predicted * 1.15)

        forecast.append({
            "date":       future_date.strftime("%Y-%m-%d"),
            "label":      future_date.strftime("%a %d %b"),
            "predicted":  predicted,
            "ci_low":     ci_low,
            "ci_high":    ci_high,
            "day_of_week": future_date.strftime("%A"),
            "season":     season,
            "festival":   festival,
            "boost_reason": f"Festival season: {festival}" if festival else (
                "Weekend peak" if dow >= 5 else None
            ),
        })

    avg_historical = round(y_mean, 1)
    peak_day = max(forecast, key=lambda x: x["predicted"]) if forecast else None

    return {
        "forecast":          forecast,
        "avg_historical":    avg_historical,
        "trend_direction":   "UP" if (slope > 0 if y_mean > 0 else False) else "DOWN" if (slope < 0 if y_mean > 0 else False) else "STABLE",
        "peak_day":          peak_day,
        "model":             "Linear Regression + DOW Seasonality",
        "data_points_used":  sum(1 for v in series if v > 0),
        "note":              "Forecast improves with more historical data. Add more completed video jobs for accuracy.",
    }


# ── Demand Forecast ───────────────────────────────────────────────────────────

@router.get("/demand-forecast")
def demand_forecast(store_id: str = "store_1", db: Session = Depends(get_db)):
    """
    Predict reorder dates per zone based on:
    - Average time between shelf-empty events
    - Last restock date
    """
    events = (
        db.query(ShelfEvent)
        .filter(ShelfEvent.store_id == store_id)
        .order_by(ShelfEvent.wall_time)
        .all()
    )

    # Group EMPTY events by zone
    zone_empties: dict[str, list] = defaultdict(list)
    zone_last_restock: dict[str, datetime.datetime] = {}

    for e in events:
        if e.zone:
            if e.event_type == "EMPTY":
                zone_empties[e.zone].append(e.wall_time)
            elif e.event_type == "RESTOCKED":
                zone_last_restock[e.zone] = e.wall_time

    today = datetime.datetime.utcnow()
    forecasts = []

    for zone, empty_times in zone_empties.items():
        if len(empty_times) < 2:
            avg_days = 7.0  # default if insufficient data
            confidence = "LOW"
        else:
            gaps = [
                (empty_times[i] - empty_times[i - 1]).total_seconds() / 86400
                for i in range(1, len(empty_times))
            ]
            avg_days   = round(statistics.mean(gaps), 1)
            confidence = "HIGH" if len(gaps) >= 5 else "MEDIUM" if len(gaps) >= 2 else "LOW"

        last_restock = zone_last_restock.get(zone, empty_times[-1] if empty_times else today)
        next_reorder = last_restock + datetime.timedelta(days=avg_days * 0.8)  # 20% buffer
        days_until   = (next_reorder - today).days

        forecasts.append({
            "zone":              zone,
            "avg_days_between_empties": avg_days,
            "last_restock":      str(last_restock)[:10],
            "predicted_reorder_date": next_reorder.strftime("%Y-%m-%d"),
            "days_until_reorder": days_until,
            "urgency":           "OVERDUE" if days_until < 0 else "TODAY" if days_until == 0 else "SOON" if days_until <= 2 else "NORMAL",
            "confidence":        confidence,
            "empty_incidents":   len(empty_times),
            "recommendation":    (
                f"Reorder NOW — overdue by {abs(days_until)} days" if days_until < 0 else
                f"Reorder today" if days_until == 0 else
                f"Reorder in {days_until} days" if days_until <= 3 else
                f"Next reorder in ~{days_until} days"
            ),
        })

    forecasts.sort(key=lambda x: x["days_until_reorder"])

    return {
        "forecasts":    forecasts,
        "total_zones":  len(forecasts),
        "overdue":      sum(1 for f in forecasts if f["urgency"] == "OVERDUE"),
        "due_soon":     sum(1 for f in forecasts if f["urgency"] in ("TODAY", "SOON")),
        "model":        "Avg inter-arrival time with 20% safety buffer",
    }


# ── Anomaly Detection ─────────────────────────────────────────────────────────

@router.post("/anomalies/scan")
def scan_anomalies(store_id: str = "store_1", db: Session = Depends(get_db)):
    """
    Auto-scan for anomalies:
    1. Crowd spike — footfall > 2σ above mean
    2. Camera offline — job with 0 detections
    3. Long dwell — person dwell > 3× average
    4. Low traffic — footfall < 50% of average (possible camera issue)
    """
    jobs = _completed_jobs(db)
    detected = []

    if not jobs:
        return {"detected": 0, "anomalies": []}

    # Build daily footfall series
    daily_footfall = [(j.result or {}).get("entries", 0) for j in jobs if j.result]
    if not daily_footfall:
        return {"detected": 0, "anomalies": []}

    mean_ff = statistics.mean(daily_footfall)
    std_ff  = statistics.stdev(daily_footfall) if len(daily_footfall) > 1 else mean_ff * 0.3

    for j in jobs:
        r       = j.result or {}
        entries = r.get("entries", 0)
        ts      = str(j.completed_at)[:16] if j.completed_at else "unknown"

        # Crowd spike
        if std_ff > 0 and entries > mean_ff + 2 * std_ff:
            dev = round((entries - mean_ff) / std_ff, 1)
            a = AnomalyLog(
                store_id=store_id,
                anomaly_type="crowd_spike",
                value=entries,
                baseline=round(mean_ff, 1),
                deviation_pct=round((entries - mean_ff) / mean_ff * 100, 1),
                severity="HIGH" if dev > 3 else "MEDIUM",
                message=f"Crowd spike detected: {entries} entries vs avg {mean_ff:.0f} ({dev}σ above normal)",
            )
            db.add(a)
            detected.append({"type": "crowd_spike", "job": j.job_id, "value": entries, "baseline": round(mean_ff, 1), "ts": ts})

        # Camera offline / zero detections
        if entries == 0 and r.get("exits", 0) == 0:
            a = AnomalyLog(
                store_id=store_id,
                anomaly_type="camera_offline",
                value=0,
                baseline=round(mean_ff, 1),
                deviation_pct=-100.0,
                severity="CRITICAL",
                message=f"Zero detections in job {j.job_id[:8]} — possible camera offline or tampered",
            )
            db.add(a)
            detected.append({"type": "camera_offline", "job": j.job_id, "value": 0, "baseline": round(mean_ff, 1), "ts": ts})

        # Low traffic (< 30% of mean, but not zero)
        elif mean_ff > 0 and 0 < entries < mean_ff * 0.3:
            a = AnomalyLog(
                store_id=store_id,
                anomaly_type="low_traffic",
                value=entries,
                baseline=round(mean_ff, 1),
                deviation_pct=round((entries - mean_ff) / mean_ff * 100, 1),
                severity="MEDIUM",
                message=f"Unusually low traffic: {entries} entries vs avg {mean_ff:.0f}",
            )
            db.add(a)
            detected.append({"type": "low_traffic", "job": j.job_id, "value": entries, "baseline": round(mean_ff, 1), "ts": ts})

        # Long dwell anomaly
        dwell = r.get("dwell", {})
        avg_dwell = dwell.get("avg_dwell_sec", 0)
        per_person = dwell.get("per_person", {})
        if isinstance(per_person, dict) and avg_dwell > 0:
            for pid, d_sec in per_person.items():
                if isinstance(d_sec, (int, float)) and d_sec > avg_dwell * 3 and d_sec > 300:
                    a = AnomalyLog(
                        store_id=store_id,
                        anomaly_type="long_dwell",
                        value=round(d_sec, 1),
                        baseline=round(avg_dwell, 1),
                        deviation_pct=round((d_sec - avg_dwell) / avg_dwell * 100, 1),
                        severity="HIGH",
                        message=f"Person #{pid} dwell {d_sec:.0f}s — 3× above avg {avg_dwell:.0f}s",
                    )
                    db.add(a)
                    detected.append({"type": "long_dwell", "person": pid, "value": round(d_sec, 1), "baseline": round(avg_dwell, 1), "ts": ts})
                    break  # one per job

    db.commit()
    return {
        "detected":  len(detected),
        "anomalies": detected[:20],
        "scanned_jobs": len(jobs),
        "message":   f"Scan complete — {len(detected)} anomalies detected across {len(jobs)} jobs",
    }


@router.get("/anomalies")
def list_anomalies(store_id: str = "store_1", limit: int = 50, db: Session = Depends(get_db)):
    logs = (
        db.query(AnomalyLog)
        .filter(AnomalyLog.store_id == store_id)
        .order_by(AnomalyLog.wall_time.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": len(logs),
        "anomalies": [
            {
                "id":            a.id,
                "type":          a.anomaly_type,
                "zone":          a.zone,
                "value":         a.value,
                "baseline":      a.baseline,
                "deviation_pct": a.deviation_pct,
                "severity":      a.severity,
                "message":       a.message,
                "resolved":      a.resolved,
                "wall_time":     str(a.wall_time)[:16],
            }
            for a in logs
        ],
        "by_type": {
            t: sum(1 for a in logs if a.anomaly_type == t)
            for t in {"crowd_spike", "camera_offline", "low_traffic", "long_dwell"}
        },
    }


# ── Camera Health ─────────────────────────────────────────────────────────────

class CameraIssueReq(BaseModel):
    camera_id:   str
    issue_type:  str   # offline | blurred | tampered | low_light
    zone:        Optional[str] = None
    description: Optional[str] = None


@router.get("/camera-health")
def camera_health(db: Session = Depends(get_db)):
    """
    Derive camera health from:
    - Jobs with 0 detections (possible offline)
    - Manual reports
    - Alert logs with camera-related messages
    """
    jobs = _completed_jobs(db)

    # Jobs with zero detections
    zero_jobs = [
        {
            "camera_id":  f"cam_{j.job_id[:6]}",
            "job_id":     j.job_id,
            "issue_type": "offline_or_empty",
            "status":     "WARNING",
            "last_seen":  str(j.completed_at)[:16] if j.completed_at else "unknown",
            "message":    "Zero detections — camera may be offline, obstructed, or misconfigured",
        }
        for j in jobs
        if j.result and j.result.get("entries", 0) == 0 and j.result.get("exits", 0) == 0
    ]

    # Camera alerts from AlertLog
    cam_alerts = (
        db.query(AlertLog)
        .filter(AlertLog.message.ilike("%camera%"))
        .order_by(AlertLog.wall_time.desc())
        .limit(10)
        .all()
    )
    alert_issues = [
        {
            "camera_id":  "system",
            "issue_type": "alert",
            "status":     "WARNING",
            "last_seen":  str(a.wall_time)[:16],
            "message":    a.message,
        }
        for a in cam_alerts
    ]

    all_issues = zero_jobs + alert_issues + list(reversed(_camera_issues[-10:]))

    # Overall health score
    total_jobs   = len(jobs)
    healthy_jobs = total_jobs - len(zero_jobs)
    health_score = round(healthy_jobs / total_jobs * 100) if total_jobs > 0 else 100

    return {
        "health_score":   health_score,
        "status":         "HEALTHY" if health_score >= 90 else "DEGRADED" if health_score >= 70 else "CRITICAL",
        "total_cameras":  max(1, total_jobs),
        "issues":         all_issues[:20],
        "total_issues":   len(all_issues),
        "recommendations": [
            "Check camera power and network connection" if any(i["issue_type"] == "offline_or_empty" for i in all_issues) else None,
            "Clean camera lens — possible blur detected" if any(i["issue_type"] == "blurred" for i in all_issues) else None,
            "Review camera placement for tamper evidence" if any(i["issue_type"] == "tampered" for i in all_issues) else None,
        ],
    }


@router.post("/camera-health/report")
def report_camera_issue(req: CameraIssueReq):
    issue = {
        "id":          len(_camera_issues) + 1,
        "camera_id":   req.camera_id,
        "issue_type":  req.issue_type,
        "zone":        req.zone,
        "description": req.description,
        "status":      "OPEN",
        "reported_at": datetime.datetime.utcnow().isoformat(),
    }
    _camera_issues.append(issue)
    return {"status": "reported", "id": issue["id"]}
