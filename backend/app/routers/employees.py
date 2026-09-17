"""
routers/employees.py — Employee Management for Retail AI
"""
import datetime
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/employees", tags=["employees"])

_employees = [
    {"id":"E101","name":"Rahul Kumar", "initials":"RK","role":"Sales Associate",  "shift":"Morning (9 AM - 5 PM)","status":"Present",     "checkin":"09:02 AM","zone":"Billing Counter 1"},
    {"id":"E102","name":"Priya Sharma","initials":"PS","role":"Cashier",           "shift":"Morning (9 AM - 5 PM)","status":"On Break",    "checkin":"09:15 AM","zone":"Billing Counter 1"},
    {"id":"E103","name":"Amit Mehta",  "initials":"AM","role":"Store Manager",     "shift":"Morning (9 AM - 5 PM)","status":"Present",     "checkin":"08:58 AM","zone":"Main Floor"},
    {"id":"E104","name":"Sneha Nair",  "initials":"SN","role":"Sales Associate",   "shift":"Evening (2 PM - 10 PM)","status":"Present",    "checkin":"02:05 PM","zone":"Fitting Room"},
    {"id":"E105","name":"Vikas Patel", "initials":"VP","role":"Cashier",           "shift":"Evening (2 PM - 10 PM)","status":"Absent",     "checkin":"--",      "zone":"Billing Counter 2"},
    {"id":"E106","name":"Aisha Khan",  "initials":"AK","role":"Sales Associate",   "shift":"Morning (9 AM - 5 PM)","status":"Present",     "checkin":"09:10 AM","zone":"Billing Counter 2"},
    {"id":"E107","name":"Rohan Tiwari","initials":"RT","role":"Floor Supervisor",  "shift":"Evening (2 PM - 10 PM)","status":"Checked Out","checkin":"09:05 AM","zone":"Main Floor"},
    {"id":"E108","name":"Neha Pawar",  "initials":"NP","role":"Sales Associate",   "shift":"Morning (9 AM - 5 PM)","status":"Present",     "checkin":"09:18 AM","zone":"Main Floor"},
]

_attendance_week = [
    {"day":"Mon","present":20,"absent":4},
    {"day":"Tue","present":22,"absent":2},
    {"day":"Wed","present":21,"absent":3},
    {"day":"Thu","present":22,"absent":2},
    {"day":"Fri","present":20,"absent":4},
    {"day":"Sat","present":19,"absent":5},
    {"day":"Sun","present":22,"absent":2},
]

_face_logs = [
    {"emp_id":"E101","name":"Rahul Kumar", "initials":"RK","camera":"Main Entrance",    "event":"Check-in","conf":98.4,"timestamp":"21 May 2025, 09:02 AM","method":"Face Recognition","liveness":True},
    {"emp_id":"E102","name":"Priya Sharma","initials":"PS","camera":"Billing Counter 1","event":"Check-in","conf":97.8,"timestamp":"21 May 2025, 09:15 AM","method":"Face Recognition","liveness":True},
    {"emp_id":"E103","name":"Amit Mehta",  "initials":"AM","camera":"Main Entrance",    "event":"Check-in","conf":99.1,"timestamp":"21 May 2025, 08:58 AM","method":"Face Recognition","liveness":True},
]

_performance = [
    {"rank":1,"emp_id":"E110","name":"Karan Shah",  "initials":"KS","sales":1245600,"txn":187,"score":92},
    {"rank":2,"emp_id":"E103","name":"Amit Mehta",  "initials":"AM","sales":982200, "txn":142,"score":88},
    {"rank":3,"emp_id":"E102","name":"Priya Sharma","initials":"PS","sales":764300, "txn":121,"score":85},
]

_payroll = [
    {"emp_id":"E101","name":"Rahul Kumar", "sched_hrs":"8h","actual_hrs":"8h 15m","overtime":"15m","leave_bal":2},
    {"emp_id":"E102","name":"Priya Sharma","sched_hrs":"8h","actual_hrs":"7h 50m","overtime":"-",  "leave_bal":1},
    {"emp_id":"E103","name":"Amit Mehta",  "sched_hrs":"8h","actual_hrs":"8h 30m","overtime":"30m","leave_bal":0},
]

_zone_assignment = [
    {"zone":"Billing Counter 1","icon":"🛒","staff":["E101","E105"],"names":["PS","VP"]},
    {"zone":"Billing Counter 2","icon":"🛒","staff":["E106","E102"],"names":["RK","AK"]},
    {"zone":"Fitting Room",     "icon":"👗","staff":["E104"],       "names":["SN"]},
    {"zone":"Main Floor",       "icon":"🏪","staff":["E103","E107","E108"],"names":["AM","RT","NP"]},
]

_anomalies = [
    {"emp_id":"E115","msg":"Unusual absence pattern — E115","detail":"Absent for 3 consecutive days","time":"10:24 AM","sev":"High"},
    {"emp_id":"E102","msg":"Extended break time — E102",    "detail":"Break time 22 min (limit 15 min)","time":"11:02 AM","sev":"Medium"},
    {"emp_id":"E107","msg":"Login from unregistered zone — E107","detail":"Detected at storage area","time":"09:18 AM","sev":"Critical"},
]

_break_status = [
    {"emp_id":"E102","name":"Priya Sharma","initials":"PS","role":"Cashier",        "break_min":22,"limit":15,"status":"Break Overrun"},
    {"emp_id":"E106","name":"Aisha Khan",  "initials":"AK","role":"Sales Associate","break_min":8, "limit":15,"status":"Within Limit"},
]

_shift_schedule = [
    {"name":"Rahul Kumar", "shifts":["Morning","Morning","Morning","Morning","Morning","Off","Off"]},
    {"name":"Priya Sharma","shifts":["Morning","Morning","Morning","Morning","Morning","Off","Off"]},
    {"name":"Amit Mehta",  "shifts":["Morning","Morning","Morning","Morning","Morning","Off","Off"]},
    {"name":"Sneha Nair",  "shifts":["Evening","Evening","Evening","Evening","Evening","Off","Off"]},
]

_productivity = [
    {"emp_id":"E110","name":"E110","sales_per_hr":1240},
    {"emp_id":"E103","name":"E103","sales_per_hr":980},
    {"emp_id":"E102","name":"E102","sales_per_hr":860},
    {"emp_id":"E108","name":"E108","sales_per_hr":720},
    {"emp_id":"E104","name":"E104","sales_per_hr":690},
]


class EmployeeCreate(BaseModel):
    name: str
    role: str
    shift: str
    zone: Optional[str] = "Main Floor"


@router.get("/list")
def list_employees():
    present = sum(1 for e in _employees if e["status"] == "Present")
    on_break = sum(1 for e in _employees if e["status"] == "On Break")
    absent = sum(1 for e in _employees if e["status"] in ("Absent", "Checked Out"))
    return {
        "employees": _employees,
        "total": len(_employees),
        "present": present,
        "on_break": on_break,
        "absent": absent,
        "attendance_pct": round(present / len(_employees) * 100),
    }


@router.get("/attendance")
def attendance():
    return {"week": _attendance_week, "total": 24, "present": 22, "on_break": 2, "absent": 2, "attendance_pct": 92}


@router.get("/face-logs")
def face_logs():
    return {"logs": _face_logs}


@router.get("/performance")
def performance():
    return {"top": _performance}


@router.get("/payroll")
def payroll():
    return {"payroll": _payroll}


@router.get("/zones")
def zone_assignments():
    return {"zones": _zone_assignment}


@router.get("/anomalies")
def anomalies():
    return {"anomalies": _anomalies}


@router.get("/breaks")
def break_status():
    return {"breaks": _break_status}


@router.get("/shifts")
def shift_schedule():
    days = ["Mon 19 May","Tue 20 May","Wed 21 May","Thu 22 May","Fri 23 May","Sat 24 May","Sun 25 May"]
    return {"schedule": _shift_schedule, "days": days}


@router.get("/productivity")
def productivity():
    return {"top5": _productivity, "top_performer": "Employee E110", "above_avg_pct": 22}


@router.post("/add")
def add_employee(emp: EmployeeCreate):
    new_id = f"E{200 + len(_employees)}"
    initials = "".join(w[0] for w in emp.name.split()[:2]).upper()
    _employees.append({
        "id": new_id, "name": emp.name, "initials": initials,
        "role": emp.role, "shift": emp.shift, "status": "Present",
        "checkin": datetime.datetime.now().strftime("%I:%M %p"), "zone": emp.zone,
    })
    return {"status": "added", "id": new_id}


@router.patch("/status/{emp_id}")
def update_status(emp_id: str, status: str):
    for e in _employees:
        if e["id"] == emp_id:
            e["status"] = status
            return {"status": "updated", "employee": e}
    return {"error": "not found"}
