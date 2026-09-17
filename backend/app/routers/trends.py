"""
routers/trends.py — Historical Trends for Retail AI
GET /trends/daily       → daily footfall for last 30 days
GET /trends/weekly      → weekly aggregated footfall
GET /trends/zones       → zone popularity over time
GET /trends/heatmap     → aggregated zone heatmap across all jobs
GET /trends/summary     → quick stats card data
"""
import datetime
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalyticsJob, JobStatus

router = APIRouter(prefix="/trends", tags=["trends"])

DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _completed_jobs(db: Session):
    return db.query(AnalyticsJob).filter(AnalyticsJob.status == JobStatus.COMPLETED).all()


# ── Daily Footfall (last 30 days) ─────────────────────────────────────────────

@router.get("/daily")
def daily_footfall(db: Session = Depends(get_db)):
    jobs = _completed_jobs(db)
    daily: dict[str, dict] = defaultdict(lambda: {"entries": 0, "exits": 0, "jobs": 0, "peak": 0})

    for j in jobs:
        if not j.completed_at or not j.result:
            continue
        day = j.completed_at.strftime("%Y-%m-%d")
        r   = j.result
        daily[day]["entries"] += r.get("entries", 0)
        daily[day]["exits"]   += r.get("exits", 0)
        daily[day]["jobs"]    += 1
        pc = r.get("peak_crowd", {})
        if isinstance(pc, dict):
            daily[day]["peak"] = max(daily[day]["peak"], pc.get("count", 0))

    # Fill last 30 days (even if no data)
    today  = datetime.date.today()
    result = []
    for i in range(29, -1, -1):
        d   = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        row = daily.get(d, {"entries": 0, "exits": 0, "jobs": 0, "peak": 0})
        result.append({"date": d, "label": d[5:], **row})  # label = MM-DD

    return {"days": result, "total_days": len(result)}


# ── Weekly Aggregated ─────────────────────────────────────────────────────────

@router.get("/weekly")
def weekly_footfall(db: Session = Depends(get_db)):
    jobs = _completed_jobs(db)
    weekly: dict[str, dict] = defaultdict(lambda: {"entries": 0, "exits": 0, "jobs": 0})

    for j in jobs:
        if not j.completed_at or not j.result:
            continue
        week = j.completed_at.strftime("%Y-W%W")
        r    = j.result
        weekly[week]["entries"] += r.get("entries", 0)
        weekly[week]["exits"]   += r.get("exits", 0)
        weekly[week]["jobs"]    += 1

    # Last 12 weeks
    today  = datetime.date.today()
    result = []
    for i in range(11, -1, -1):
        d    = today - datetime.timedelta(weeks=i)
        week = d.strftime("%Y-W%W")
        row  = weekly.get(week, {"entries": 0, "exits": 0, "jobs": 0})
        result.append({"week": week, "label": f"W{d.strftime('%W')}", **row})

    return {"weeks": result}


# ── Day-of-Week Pattern ───────────────────────────────────────────────────────

@router.get("/day-pattern")
def day_of_week_pattern(db: Session = Depends(get_db)):
    """Average footfall by day of week (Mon–Sun)."""
    jobs = _completed_jobs(db)
    dow_entries: dict[int, list] = defaultdict(list)
    dow_exits:   dict[int, list] = defaultdict(list)

    for j in jobs:
        if not j.completed_at or not j.result:
            continue
        dow = j.completed_at.weekday()  # 0=Mon, 6=Sun
        r   = j.result
        dow_entries[dow].append(r.get("entries", 0))
        dow_exits[dow].append(r.get("exits", 0))

    result = []
    for i in range(7):
        entries_list = dow_entries.get(i, [0])
        exits_list   = dow_exits.get(i, [0])
        result.append({
            "day":          DAYS_OF_WEEK[i],
            "avg_entries":  round(sum(entries_list) / len(entries_list), 1),
            "avg_exits":    round(sum(exits_list)   / len(exits_list),   1),
            "sample_count": len(entries_list),
        })

    return {"pattern": result}


# ── Zone Popularity Over Time ─────────────────────────────────────────────────

@router.get("/zones")
def zone_trends(db: Session = Depends(get_db)):
    jobs = _completed_jobs(db)
    zone_totals: dict[str, int] = defaultdict(int)
    zone_by_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for j in jobs:
        if not j.result or not j.completed_at:
            continue
        day   = j.completed_at.strftime("%Y-%m-%d")
        zones = j.result.get("zones", {})
        uv    = zones.get("unique_visitors", {})
        for zone, count in uv.items():
            zone_totals[zone] += count
            zone_by_day[day][zone] += count

    # Last 14 days
    today  = datetime.date.today()
    days   = [(today - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    all_zones = list(zone_totals.keys())

    timeline = []
    for d in days:
        row = {"date": d, "label": d[5:]}
        for z in all_zones:
            row[z] = zone_by_day[d].get(z, 0)
        timeline.append(row)

    return {
        "zones":       all_zones,
        "zone_totals": dict(zone_totals),
        "timeline":    timeline,
        "most_popular": max(zone_totals, key=zone_totals.get) if zone_totals else None,
    }


# ── Aggregated Heatmap ────────────────────────────────────────────────────────

@router.get("/heatmap")
def aggregated_heatmap(db: Session = Depends(get_db)):
    """Sum unique_visitors per zone across all completed jobs."""
    jobs = _completed_jobs(db)
    heatmap: dict[str, int] = defaultdict(int)

    for j in jobs:
        if not j.result:
            continue
        zones = j.result.get("zones", {})
        uv    = zones.get("unique_visitors", {})
        for zone, count in uv.items():
            heatmap[zone] += count

    total = sum(heatmap.values()) or 1
    result = {
        zone: {
            "count":   count,
            "pct":     round(count / total * 100, 1),
        }
        for zone, count in sorted(heatmap.items(), key=lambda x: -x[1])
    }
    return {"heatmap": result, "total_visitors": total}


# ── Summary Stats ─────────────────────────────────────────────────────────────

@router.get("/summary")
def trends_summary(db: Session = Depends(get_db)):
    jobs = _completed_jobs(db)
    if not jobs:
        return {"total_jobs": 0, "total_entries": 0, "total_exits": 0,
                "avg_entries_per_job": 0, "busiest_day": None, "top_zone": None}

    total_entries = sum((j.result or {}).get("entries", 0) for j in jobs)
    total_exits   = sum((j.result or {}).get("exits",   0) for j in jobs)

    # Busiest day
    daily: dict[str, int] = defaultdict(int)
    for j in jobs:
        if j.completed_at and j.result:
            day = j.completed_at.strftime("%Y-%m-%d")
            daily[day] += (j.result or {}).get("entries", 0)
    busiest_day = max(daily, key=daily.get) if daily else None

    # Top zone overall
    zone_totals: dict[str, int] = defaultdict(int)
    for j in jobs:
        zones = (j.result or {}).get("zones", {})
        for z, c in zones.get("unique_visitors", {}).items():
            zone_totals[z] += c
    top_zone = max(zone_totals, key=zone_totals.get) if zone_totals else None

    return {
        "total_jobs":          len(jobs),
        "total_entries":       total_entries,
        "total_exits":         total_exits,
        "avg_entries_per_job": round(total_entries / len(jobs), 1),
        "busiest_day":         busiest_day,
        "top_zone":            top_zone,
    }
