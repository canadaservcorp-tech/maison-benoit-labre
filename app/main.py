"""MBL Building Maintenance System - backend.

Minimal FastAPI backend restoring service for the previously deployed
`mbl-frontend` SPA. The frontend bundle (`index-B-irygFq.js`) expects the
endpoints and response shapes implemented here.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

# --- Configuration -----------------------------------------------------------

DATA_DIR = Path(os.environ.get("MBL_DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "mbl.sqlite3"

JWT_SECRET = os.environ.get("MBL_JWT_SECRET", "mbl-dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_TTL_HOURS = 24 * 14  # 2 weeks

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


# --- DB helpers --------------------------------------------------------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(db()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                is_approver INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS apartments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                building TEXT,
                floor TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS common_areas (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                contact_name TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                rating REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inventory (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                quantity INTEGER DEFAULT 0,
                min_quantity INTEGER DEFAULT 0,
                unit TEXT,
                location TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                location TEXT,
                serial_number TEXT,
                purchase_date TEXT,
                condition TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                condition TEXT,
                location TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS remarks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                category TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS maintenance_requests (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'open',
                location TEXT,
                apartment_id TEXT,
                reported_by TEXT,
                assigned_to TEXT,
                cost REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                task_type TEXT,
                due_date TEXT,
                recurrence TEXT,
                recurrence_interval INTEGER DEFAULT 1,
                priority TEXT DEFAULT 'medium',
                assigned_to TEXT,
                reminder_days INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS historical_records (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                date TEXT,
                category TEXT,
                contractor_name TEXT,
                contractor_contact TEXT,
                cost REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


def seed_users() -> None:
    seeds = [
        {
            "email": "admin@mbl.com",
            "password": "Admin2025!",
            "name": "Admin",
            "role": "admin",
            "is_approver": 1,
        },
        {
            "email": "andreanedesilets@lamaisonbenoitlabre.org",
            "password": "Andreanne2025!",
            "name": "Andréanne Desilets",
            "role": "admin",
            "is_approver": 1,
        },
        {
            "email": "faycal@lamaisonbenoitlabre.org",
            "password": "Faycal2025!",
            "name": "Faycal",
            "role": "admin",
            "is_approver": 1,
        },
        {
            "email": "hicham@lamaisonbenoitlabre.org",
            "password": "Hicham2025!",
            "name": "Hicham",
            "role": "admin",
            "is_approver": 1,
        },
    ]
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as conn, conn:
        for s in seeds:
            row = conn.execute(
                "SELECT id FROM users WHERE email = ?", (s["email"],)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, name, role, is_approver, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        s["email"],
                        pwd_context.hash(s["password"]),
                        s["name"],
                        s["role"],
                        s["is_approver"],
                        now,
                    ),
                )


# --- Auth --------------------------------------------------------------------

def user_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "is_approver": bool(row["is_approver"]),
    }


def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_TTL_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, Any]:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user_to_dict(row)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# --- App ---------------------------------------------------------------------

app = FastAPI(title="MBL Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_users()


@app.get("/")
def root() -> dict:
    return {"service": "mbl-backend", "status": "ok"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# --- Auth routes -------------------------------------------------------------

class LoginIn(BaseModel):
    email: EmailStr
    password: str


@app.post("/api/auth/login")
def login(data: LoginIn) -> dict:
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (data.email.lower(),)
        ).fetchone()
    if row is None or not pwd_context.verify(data.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": make_token(row["id"]), "user": user_to_dict(row)}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": user}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "employee"


@app.post("/api/auth/register")
def register(
    data: RegisterIn, _admin: dict = Depends(require_admin)
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())
    is_approver = 1 if data.role == "admin" else 0
    with closing(db()) as conn, conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (data.email.lower(),)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="User already exists")
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, role, is_approver, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_id,
                data.email.lower(),
                pwd_context.hash(data.password),
                data.name,
                data.role,
                is_approver,
                now,
            ),
        )
    return {"success": True, "user_id": new_id}


@app.get("/api/user/is-approver")
def is_approver(user: dict = Depends(get_current_user)) -> dict:
    return {"is_approver": user["is_approver"]}


# --- Generic listing helper --------------------------------------------------

def _list(table: str) -> list[dict]:
    with closing(db()) as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


# --- Dashboard ---------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(_user: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        stats_rows = conn.execute(
            "SELECT status, COUNT(*) as c, COALESCE(SUM(cost),0) as total "
            "FROM maintenance_requests GROUP BY status"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(cost),0) as total FROM maintenance_requests"
        ).fetchone()
        apartments = conn.execute("SELECT COUNT(*) c FROM apartments").fetchone()["c"]
        employees = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        recent = conn.execute(
            "SELECT * FROM maintenance_requests ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

    by_status = {r["status"]: r["c"] for r in stats_rows}
    stats = {
        "total_requests": total["c"],
        "open_requests": by_status.get("open", 0) + by_status.get("in_progress", 0),
        "completed_requests": by_status.get("completed", 0),
        "pending_requests": by_status.get("pending", 0),
        "total_cost": total["total"] or 0,
        "total_apartments": apartments,
        "total_employees": employees,
    }
    return {"stats": stats, "recent_requests": [dict(r) for r in recent]}


# --- Apartments / common areas ----------------------------------------------

@app.get("/api/apartments")
def list_apartments(_u: dict = Depends(get_current_user)) -> dict:
    return {"apartments": _list("apartments"), "success": True}


@app.get("/api/apartments/work-status")
def apartments_work_status(_u: dict = Depends(get_current_user)) -> dict:
    # Aggregate open requests per apartment.
    with closing(db()) as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.name, a.building, a.floor,
                   COALESCE(SUM(CASE WHEN m.status IN ('open','in_progress','pending') THEN 1 ELSE 0 END), 0) AS open_count,
                   COALESCE(SUM(CASE WHEN m.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_count
            FROM apartments a
            LEFT JOIN maintenance_requests m ON m.apartment_id = a.id
            GROUP BY a.id
            ORDER BY a.name
            """
        ).fetchall()
    return {"apartments": [dict(r) for r in rows]}


@app.get("/api/common-areas")
def list_common_areas(_u: dict = Depends(get_current_user)) -> dict:
    return {"common_areas": _list("common_areas"), "success": True}


# --- Suppliers ---------------------------------------------------------------

@app.get("/api/suppliers")
def list_suppliers(_u: dict = Depends(get_current_user)) -> dict:
    return {"suppliers": _list("suppliers"), "success": True}


# --- Employees ---------------------------------------------------------------

@app.get("/api/employees")
def list_employees(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id, email, name, role, is_approver, created_at FROM users ORDER BY name"
        ).fetchall()
    return {
        "success": True,
        "employees": [
            {**dict(r), "is_approver": bool(r["is_approver"])} for r in rows
        ],
    }


# --- Inventory / assets / tools / remarks -----------------------------------

@app.get("/api/inventory")
def list_inventory(_u: dict = Depends(get_current_user)) -> dict:
    return {"inventory": _list("inventory"), "success": True}


@app.get("/api/inventory/low-stock")
def low_stock(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE quantity <= min_quantity ORDER BY name"
        ).fetchall()
    return {"low_stock_items": [dict(r) for r in rows]}


@app.get("/api/assets")
def list_assets(_u: dict = Depends(get_current_user)) -> dict:
    return {"assets": _list("assets"), "success": True}


@app.get("/api/tools")
def list_tools(_u: dict = Depends(get_current_user)) -> dict:
    return {"tools": _list("tools"), "success": True}


@app.get("/api/remarks")
def list_remarks(
    _u: dict = Depends(get_current_user), category: str | None = None
) -> dict:
    with closing(db()) as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM remarks WHERE category = ? ORDER BY created_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM remarks ORDER BY created_at DESC"
            ).fetchall()
    return {"remarks": [dict(r) for r in rows]}


# --- Maintenance requests ---------------------------------------------------

@app.get("/api/maintenance")
def list_maintenance(
    _u: dict = Depends(get_current_user),
    status: str | None = None,
    priority: str | None = None,
) -> dict:
    sql = "SELECT * FROM maintenance_requests"
    where = []
    params: list = []
    if status:
        where.append("status = ?")
        params.append(status)
    if priority:
        where.append("priority = ?")
        params.append(priority)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    with closing(db()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"maintenance_requests": [dict(r) for r in rows]}


# --- Scheduled tasks --------------------------------------------------------

@app.get("/api/scheduled-tasks")
def list_scheduled_tasks(_u: dict = Depends(get_current_user)) -> dict:
    return {"scheduled_tasks": _list("scheduled_tasks"), "success": True}


@app.get("/api/scheduled-tasks/upcoming")
def upcoming_tasks(
    _u: dict = Depends(get_current_user), days: int = 14
) -> dict:
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks "
            "WHERE status != 'completed' AND due_date IS NOT NULL "
            "AND due_date BETWEEN ? AND ? ORDER BY due_date ASC",
            (now, cutoff),
        ).fetchall()
    return {"upcoming_tasks": [dict(r) for r in rows]}


@app.get("/api/scheduled-tasks/overdue")
def overdue_tasks(_u: dict = Depends(get_current_user)) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks "
            "WHERE status != 'completed' AND due_date IS NOT NULL "
            "AND due_date < ? ORDER BY due_date ASC",
            (now,),
        ).fetchall()
    return {"overdue_tasks": [dict(r) for r in rows]}


# --- Historical records -----------------------------------------------------

@app.get("/api/historical-records")
def list_historical(_u: dict = Depends(get_current_user)) -> dict:
    return {"success": True, "records": _list("historical_records")}


# --- Analytics --------------------------------------------------------------

@app.get("/api/analytics/costs")
def analytics_costs(
    _u: dict = Depends(get_current_user),
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    with closing(db()) as conn:
        total_row = conn.execute(
            "SELECT COALESCE(SUM(cost),0) AS total, COUNT(*) AS c FROM maintenance_requests"
        ).fetchone()
    return {
        "total_cost": total_row["total"] or 0,
        "total_requests": total_row["c"],
        "costs_by_month": [],
        "costs_by_category": [],
        "costs_by_apartment": [],
    }


@app.get("/api/analytics/yearly-summary")
def yearly_summary(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT substr(created_at, 1, 4) AS year, "
            "COUNT(*) AS total_requests, "
            "COALESCE(SUM(cost),0) AS total_cost "
            "FROM maintenance_requests GROUP BY year ORDER BY year DESC"
        ).fetchall()
    return [
        {
            "year": r["year"],
            "total_requests": r["total_requests"],
            "total_cost": r["total_cost"] or 0,
        }
        for r in rows
    ]


@app.get("/api/analytics/apartment/{apartment_id}")
def analytics_apartment(
    apartment_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total_requests, COALESCE(SUM(cost),0) AS total_cost "
            "FROM maintenance_requests WHERE apartment_id = ?",
            (apartment_id,),
        ).fetchone()
    return {
        "apartment_id": apartment_id,
        "total_requests": row["total_requests"],
        "total_cost": row["total_cost"] or 0,
        "recent_requests": [],
    }


# --- Catch-all: log unknown API calls for debugging --------------------------

@app.middleware("http")
async def log_unhandled(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404 and request.url.path.startswith("/api/"):
        print(f"[404] {request.method} {request.url.path}")
    return response
