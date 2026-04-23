"""MBL Building Maintenance System - backend.

FastAPI backend restoring service for the `mbl-frontend` SPA. Endpoint
contracts and payload shapes are derived from the minified production bundle
so the existing frontend works unchanged.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
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
JWT_TTL_HOURS = 24 * 14

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


# --- DB helpers --------------------------------------------------------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    building TEXT,
    floor TEXT,
    apt_number TEXT,
    tenant_name TEXT,
    tenant_phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS common_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT,
    area_type TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    service_type TEXT,
    phone TEXT,
    mobile TEXT,
    email TEXT,
    website TEXT,
    address TEXT,
    scope TEXT,
    notes TEXT,
    rating REAL DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS supplier_ratings (
    id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    rating REAL NOT NULL,
    comment TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY,
    item_name TEXT NOT NULL,
    category TEXT,
    quantity INTEGER DEFAULT 0,
    min_quantity INTEGER DEFAULT 0,
    unit TEXT,
    location TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    serial_number TEXT,
    category TEXT,
    department TEXT,
    location_type TEXT,
    location_id INTEGER,
    purchase_date TEXT,
    purchase_value REAL DEFAULT 0,
    condition TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    serial_number TEXT,
    category TEXT,
    purchase_date TEXT,
    purchase_cost REAL DEFAULT 0,
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
    category TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    location_type TEXT,
    location_id INTEGER,
    apartment_id TEXT,
    reported_by TEXT,
    assigned_to TEXT,
    supplier_id TEXT,
    cost REAL DEFAULT 0,
    approval_status TEXT,
    approved_by TEXT,
    approved_at TEXT,
    rejected_by TEXT,
    rejected_at TEXT,
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
    location_type TEXT,
    location_id INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS historical_records (
    id TEXT PRIMARY KEY,
    work_date TEXT,
    scope TEXT,
    category TEXT,
    description TEXT,
    location TEXT,
    contractor_name TEXT,
    contractor_contact TEXT,
    cost REAL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL
);
"""


SCHEMA_VERSION = 2


def init_db() -> None:
    # Wipe the DB on schema version bump. Safe while we have no real data yet;
    # once production data is being entered, replace this with proper migrations.
    with closing(db()) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        row = conn.execute(
            "SELECT value FROM _meta WHERE key='schema_version'"
        ).fetchone()
        current = int(row["value"]) if row else 0
        if current < SCHEMA_VERSION:
            # Drop all tables (except _meta) and recreate
            tables = [
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name != '_meta'"
                ).fetchall()
            ]
            for t in tables:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO _meta (key,value) VALUES ('schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
        else:
            conn.executescript(SCHEMA)


def seed_users() -> None:
    seeds = [
        ("admin@mbl.com", "Admin2025!", "Admin", "admin", 1),
        ("andreanedesilets@lamaisonbenoitlabre.org", "Andreanne2025!",
         "Andréanne Desilets", "admin", 1),
        ("faycal@lamaisonbenoitlabre.org", "Faycal2025!", "Faycal", "admin", 1),
        ("hicham@lamaisonbenoitlabre.org", "Hicham2025!", "Hicham", "admin", 1),
    ]
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as conn, conn:
        for email, pw, name, role, approver in seeds:
            if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                continue
            conn.execute(
                "INSERT INTO users (id,email,password_hash,name,role,is_approver,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), email, pwd_context.hash(pw), name, role, approver, now),
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
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
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
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
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
            "SELECT * FROM users WHERE email=?", (data.email.lower(),)
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
def register(data: RegisterIn, _admin: dict = Depends(require_admin)) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())
    is_approver = 1 if data.role == "admin" else 0
    with closing(db()) as conn, conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE email=?", (data.email.lower(),)
        ).fetchone():
            raise HTTPException(status_code=400, detail="User already exists")
        conn.execute(
            "INSERT INTO users (id,email,password_hash,name,role,is_approver,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (new_id, data.email.lower(), pwd_context.hash(data.password),
             data.name, data.role, is_approver, now),
        )
    return {"success": True, "user_id": new_id}


@app.delete("/api/employees/{employee_id}")
def delete_employee(
    employee_id: str, admin: dict = Depends(require_admin)
) -> dict:
    if employee_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    with closing(db()) as conn, conn:
        r = conn.execute("DELETE FROM users WHERE id=?", (employee_id,))
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True}


@app.get("/api/user/is-approver")
def is_approver(user: dict = Depends(get_current_user)) -> dict:
    return {"is_approver": user["is_approver"]}


# --- Generic helpers --------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list(table: str) -> list[dict]:
    with closing(db()) as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM {table} ORDER BY created_at DESC"
        ).fetchall()]


def _insert(table: str, data: dict, id_field: str = "id",
            int_id: bool = False) -> dict:
    data = {k: v for k, v in data.items() if v is not None}
    data["created_at"] = _now()
    if not int_id:
        data.setdefault(id_field, str(uuid.uuid4()))
    cols = ", ".join(data.keys())
    ph = ", ".join("?" * len(data))
    with closing(db()) as conn, conn:
        cur = conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({ph})", tuple(data.values())
        )
        if int_id:
            data[id_field] = cur.lastrowid
    return data


def _update(table: str, pk: Any, data: dict) -> dict:
    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        with closing(db()) as conn:
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id=?", (pk,)
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return dict(row)
    set_clause = ", ".join(f"{k}=?" for k in data.keys())
    with closing(db()) as conn, conn:
        cur = conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE id=?",
            (*data.values(), pk),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (pk,)).fetchone()
    return dict(row)


def _delete(table: str, pk: Any) -> None:
    with closing(db()) as conn, conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (pk,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")


# --- Dashboard ---------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(_user: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        stats_rows = conn.execute(
            "SELECT status, COUNT(*) as c FROM maintenance_requests GROUP BY status"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(cost),0) total FROM maintenance_requests"
        ).fetchone()
        apartments = conn.execute("SELECT COUNT(*) c FROM apartments").fetchone()["c"]
        employees = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        suppliers = conn.execute("SELECT COUNT(*) c FROM suppliers").fetchone()["c"]
        assets = conn.execute("SELECT COUNT(*) c FROM assets").fetchone()["c"]
        low = conn.execute(
            "SELECT COUNT(*) c FROM inventory WHERE quantity <= min_quantity"
        ).fetchone()["c"]
        recent = conn.execute(
            "SELECT * FROM maintenance_requests ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
    by = {r["status"]: r["c"] for r in stats_rows}
    stats = {
        "total_requests": total["c"],
        "pending_requests": by.get("pending", 0) + by.get("pending_approval", 0),
        "open_requests": by.get("open", 0),
        "in_progress_requests": by.get("in_progress", 0),
        "completed_requests": by.get("completed", 0),
        "total_cost": total["total"] or 0,
        "total_apartments": apartments,
        "total_employees": employees,
        "total_suppliers": suppliers,
        "total_assets": assets,
        "low_stock_count": low,
    }
    return {"stats": stats, "recent_requests": [dict(r) for r in recent]}


# --- Apartments / common areas ----------------------------------------------

class ApartmentIn(BaseModel):
    name: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    apt_number: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_phone: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/apartments")
def list_apartments(_u: dict = Depends(get_current_user)) -> dict:
    return {"apartments": _list("apartments"), "success": True}


@app.post("/api/apartments")
def create_apartment(
    data: ApartmentIn, _u: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("name"):
        raise HTTPException(status_code=400, detail="name is required")
    row = _insert("apartments", d, int_id=True)
    return {"success": True, "apartment": row}


@app.put("/api/apartments/{apartment_id}")
def update_apartment(
    apartment_id: int,
    tenant_name: Optional[str] = Query(None),
    tenant_phone: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    building: Optional[str] = Query(None),
    floor: Optional[str] = Query(None),
    apt_number: Optional[str] = Query(None),
    _u: dict = Depends(get_current_user),
) -> dict:
    # Frontend sends fields as query params via URLSearchParams
    data = {
        "tenant_name": tenant_name, "tenant_phone": tenant_phone,
        "notes": notes, "name": name, "building": building,
        "floor": floor, "apt_number": apt_number,
    }
    row = _update("apartments", apartment_id, data)
    return {"success": True, "apartment": row}


@app.delete("/api/apartments/{apartment_id}")
def delete_apartment(
    apartment_id: int, _u: dict = Depends(require_admin)
) -> dict:
    _delete("apartments", apartment_id)
    return {"success": True}


@app.get("/api/apartments/work-status")
def apartments_work_status(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            """
            SELECT a.*,
                   COALESCE(SUM(CASE WHEN m.status IN ('open','in_progress','pending') THEN 1 ELSE 0 END), 0) AS open_count,
                   COALESCE(SUM(CASE WHEN m.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_count
            FROM apartments a
            LEFT JOIN maintenance_requests m ON CAST(m.location_id AS TEXT) = CAST(a.id AS TEXT) AND m.location_type='apartment'
            GROUP BY a.id
            ORDER BY a.name
            """
        ).fetchall()
    return {"apartments": [dict(r) for r in rows]}


class CommonAreaIn(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    area_type: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/common-areas")
def list_common_areas(_u: dict = Depends(get_current_user)) -> dict:
    return {"common_areas": _list("common_areas"), "success": True}


@app.post("/api/common-areas")
def create_common_area(
    data: CommonAreaIn, _u: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("name"):
        raise HTTPException(status_code=400, detail="name is required")
    row = _insert("common_areas", d, int_id=True)
    return {"success": True, "common_area": row}


@app.delete("/api/common-areas/{area_id}")
def delete_common_area(
    area_id: int, _u: dict = Depends(require_admin)
) -> dict:
    _delete("common_areas", area_id)
    return {"success": True}


# --- Suppliers ---------------------------------------------------------------

class SupplierIn(BaseModel):
    name: Optional[str] = None
    service_type: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    scope: Optional[str] = None
    notes: Optional[str] = None


class SupplierRatingIn(BaseModel):
    rating: float
    comment: Optional[str] = ""


@app.get("/api/suppliers")
def list_suppliers(_u: dict = Depends(get_current_user)) -> dict:
    return {"suppliers": _list("suppliers"), "success": True}


@app.post("/api/suppliers")
def create_supplier(
    data: SupplierIn, _u: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("name"):
        raise HTTPException(status_code=400, detail="name is required")
    row = _insert("suppliers", d)
    return {"success": True, "supplier": row}


@app.delete("/api/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: str, _u: dict = Depends(require_admin)
) -> dict:
    _delete("suppliers", supplier_id)
    return {"success": True}


@app.post("/api/suppliers/{supplier_id}/rate")
def rate_supplier(
    supplier_id: str,
    data: SupplierRatingIn,
    user: dict = Depends(get_current_user),
) -> dict:
    with closing(db()) as conn, conn:
        if not conn.execute(
            "SELECT 1 FROM suppliers WHERE id=?", (supplier_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Supplier not found")
        conn.execute(
            "INSERT INTO supplier_ratings (id,supplier_id,rating,comment,created_by,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), supplier_id, data.rating,
             data.comment or "", user["id"], _now()),
        )
        agg = conn.execute(
            "SELECT AVG(rating) avg, COUNT(*) c FROM supplier_ratings WHERE supplier_id=?",
            (supplier_id,),
        ).fetchone()
        conn.execute(
            "UPDATE suppliers SET rating=?, rating_count=? WHERE id=?",
            (agg["avg"] or 0, agg["c"], supplier_id),
        )
    return {"success": True, "rating": agg["avg"] or 0, "count": agg["c"]}


# --- Employees ---------------------------------------------------------------

@app.get("/api/employees")
def list_employees(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id,email,name,role,is_approver,created_at FROM users ORDER BY name"
        ).fetchall()
    return {
        "success": True,
        "employees": [
            {**dict(r), "is_approver": bool(r["is_approver"])} for r in rows
        ],
    }


# --- Inventory --------------------------------------------------------------

class InventoryIn(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    min_quantity: Optional[int] = None
    unit: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/inventory")
def list_inventory(_u: dict = Depends(get_current_user)) -> dict:
    return {"inventory": _list("inventory"), "success": True}


@app.get("/api/inventory/low-stock")
def low_stock(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE quantity <= min_quantity ORDER BY item_name"
        ).fetchall()
    return {"low_stock_items": [dict(r) for r in rows]}


@app.post("/api/inventory")
def create_inventory(
    data: InventoryIn, _u: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("item_name"):
        raise HTTPException(status_code=400, detail="item_name is required")
    row = _insert("inventory", d)
    return {"success": True, "item": row}


@app.put("/api/inventory/{item_id}")
def update_inventory(
    item_id: str, data: InventoryIn, _u: dict = Depends(get_current_user)
) -> dict:
    row = _update("inventory", item_id, data.model_dump(exclude_none=True))
    return {"success": True, "item": row}


@app.delete("/api/inventory/{item_id}")
def delete_inventory(
    item_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("inventory", item_id)
    return {"success": True}


# --- Assets -----------------------------------------------------------------

class AssetIn(BaseModel):
    name: Optional[str] = None
    serial_number: Optional[str] = None
    category: Optional[str] = None
    department: Optional[str] = None
    location_type: Optional[str] = None
    location_id: Optional[int] = None
    purchase_date: Optional[str] = None
    purchase_value: Optional[float] = None
    condition: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/assets")
def list_assets(_u: dict = Depends(get_current_user)) -> dict:
    return {"assets": _list("assets"), "success": True}


@app.post("/api/assets")
def create_asset(
    data: AssetIn, _u: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("name"):
        raise HTTPException(status_code=400, detail="name is required")
    row = _insert("assets", d)
    return {"success": True, "asset": row}


@app.put("/api/assets/{asset_id}")
def update_asset(
    asset_id: str,
    name: Optional[str] = Query(None),
    serial_number: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    location_type: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    purchase_date: Optional[str] = Query(None),
    purchase_value: Optional[float] = Query(None),
    condition: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    _u: dict = Depends(get_current_user),
) -> dict:
    data = {
        "name": name, "serial_number": serial_number, "category": category,
        "department": department, "location_type": location_type,
        "location_id": location_id, "purchase_date": purchase_date,
        "purchase_value": purchase_value, "condition": condition, "notes": notes,
    }
    row = _update("assets", asset_id, data)
    return {"success": True, "asset": row}


@app.delete("/api/assets/{asset_id}")
def delete_asset(
    asset_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("assets", asset_id)
    return {"success": True}


# --- Tools ------------------------------------------------------------------

class ToolIn(BaseModel):
    name: Optional[str] = None
    serial_number: Optional[str] = None
    category: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_cost: Optional[float] = None
    condition: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/tools")
def list_tools(_u: dict = Depends(get_current_user)) -> dict:
    return {"tools": _list("tools"), "success": True}


@app.post("/api/tools")
def create_tool(data: ToolIn, _u: dict = Depends(get_current_user)) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("name"):
        raise HTTPException(status_code=400, detail="name is required")
    row = _insert("tools", d)
    return {"success": True, "tool": row}


@app.put("/api/tools/{tool_id}")
def update_tool(
    tool_id: str, data: ToolIn, _u: dict = Depends(get_current_user)
) -> dict:
    row = _update("tools", tool_id, data.model_dump(exclude_none=True))
    return {"success": True, "tool": row}


@app.delete("/api/tools/{tool_id}")
def delete_tool(
    tool_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("tools", tool_id)
    return {"success": True}


# --- Remarks ----------------------------------------------------------------

class RemarkIn(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None


@app.get("/api/remarks")
def list_remarks(
    _u: dict = Depends(get_current_user), category: Optional[str] = None
) -> dict:
    with closing(db()) as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM remarks WHERE category=? ORDER BY created_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM remarks ORDER BY created_at DESC"
            ).fetchall()
    return {"remarks": [dict(r) for r in rows]}


@app.post("/api/remarks")
def create_remark(
    data: RemarkIn, user: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("title"):
        raise HTTPException(status_code=400, detail="title is required")
    d["created_by"] = user["id"]
    row = _insert("remarks", d)
    return {"success": True, "remark": row}


@app.delete("/api/remarks/{remark_id}")
def delete_remark(
    remark_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("remarks", remark_id)
    return {"success": True}


# --- Maintenance requests ---------------------------------------------------

class MaintenanceIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    location_type: Optional[str] = None
    location_id: Optional[int] = None
    apartment_id: Optional[str] = None
    assigned_to: Optional[str] = None
    supplier_id: Optional[str] = None
    cost: Optional[float] = None


@app.get("/api/maintenance")
def list_maintenance(
    _u: dict = Depends(get_current_user),
    status: Optional[str] = None,
    priority: Optional[str] = None,
) -> dict:
    sql = "SELECT * FROM maintenance_requests"
    where, params = [], []
    if status:
        where.append("status=?")
        params.append(status)
    if priority:
        where.append("priority=?")
        params.append(priority)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    with closing(db()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"maintenance_requests": [dict(r) for r in rows]}


@app.post("/api/maintenance")
def create_maintenance(
    data: MaintenanceIn, user: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("title"):
        raise HTTPException(status_code=400, detail="title is required")
    d.setdefault("status", "open")
    d.setdefault("approval_status", "pending_approval")
    d["reported_by"] = user["id"]
    row = _insert("maintenance_requests", d)
    return {"success": True, "maintenance_request": row}


@app.put("/api/maintenance/{req_id}")
def update_maintenance(
    req_id: str, data: MaintenanceIn, _u: dict = Depends(get_current_user)
) -> dict:
    row = _update("maintenance_requests", req_id,
                  data.model_dump(exclude_none=True))
    return {"success": True, "maintenance_request": row}


@app.delete("/api/maintenance/{req_id}")
def delete_maintenance(
    req_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("maintenance_requests", req_id)
    return {"success": True}


@app.post("/api/maintenance/{req_id}/approve")
def approve_maintenance(
    req_id: str, user: dict = Depends(get_current_user)
) -> dict:
    if not user["is_approver"]:
        raise HTTPException(status_code=403, detail="Not an approver")
    row = _update("maintenance_requests", req_id, {
        "approval_status": "approved",
        "approved_by": user["id"],
        "approved_at": _now(),
        "status": "in_progress",
    })
    return {"success": True, "maintenance_request": row}


@app.post("/api/maintenance/{req_id}/reject")
def reject_maintenance(
    req_id: str, user: dict = Depends(get_current_user)
) -> dict:
    if not user["is_approver"]:
        raise HTTPException(status_code=403, detail="Not an approver")
    row = _update("maintenance_requests", req_id, {
        "approval_status": "rejected",
        "rejected_by": user["id"],
        "rejected_at": _now(),
        "status": "rejected",
    })
    return {"success": True, "maintenance_request": row}


# --- Scheduled tasks --------------------------------------------------------

class ScheduledTaskIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    due_date: Optional[str] = None
    recurrence: Optional[str] = None
    recurrence_interval: Optional[int] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    reminder_days: Optional[int] = None
    location_type: Optional[str] = None
    location_id: Optional[int] = None
    status: Optional[str] = None


@app.get("/api/scheduled-tasks")
def list_scheduled_tasks(_u: dict = Depends(get_current_user)) -> dict:
    tasks = _list("scheduled_tasks")
    # Frontend uses both `scheduled_tasks` and `tasks` keys depending on screen.
    return {"scheduled_tasks": tasks, "tasks": tasks, "success": True}


@app.get("/api/scheduled-tasks/upcoming")
def upcoming_tasks(
    _u: dict = Depends(get_current_user), days: int = 14
) -> dict:
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    now = _now()
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks "
            "WHERE status!='completed' AND due_date IS NOT NULL "
            "AND due_date BETWEEN ? AND ? ORDER BY due_date ASC",
            (now, cutoff),
        ).fetchall()
    return {"upcoming_tasks": [dict(r) for r in rows]}


@app.get("/api/scheduled-tasks/overdue")
def overdue_tasks(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks "
            "WHERE status!='completed' AND due_date IS NOT NULL AND due_date<? "
            "ORDER BY due_date ASC",
            (_now(),),
        ).fetchall()
    return {"overdue_tasks": [dict(r) for r in rows]}


@app.post("/api/scheduled-tasks")
def create_scheduled_task(
    data: ScheduledTaskIn, _u: dict = Depends(get_current_user)
) -> dict:
    d = data.model_dump(exclude_none=True)
    if not d.get("title"):
        raise HTTPException(status_code=400, detail="title is required")
    row = _insert("scheduled_tasks", d)
    return {"success": True, "task": row}


@app.put("/api/scheduled-tasks/{task_id}")
def update_scheduled_task(
    task_id: str, data: ScheduledTaskIn, _u: dict = Depends(get_current_user)
) -> dict:
    row = _update("scheduled_tasks", task_id, data.model_dump(exclude_none=True))
    return {"success": True, "task": row}


@app.put("/api/scheduled-tasks/{task_id}/complete")
def complete_scheduled_task(
    task_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    row = _update("scheduled_tasks", task_id, {
        "status": "completed", "completed_at": _now()
    })
    return {"success": True, "task": row}


@app.delete("/api/scheduled-tasks/{task_id}")
def delete_scheduled_task(
    task_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("scheduled_tasks", task_id)
    return {"success": True}


# --- Historical records -----------------------------------------------------

class HistoricalIn(BaseModel):
    work_date: Optional[str] = None
    scope: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    contractor_name: Optional[str] = None
    contractor_contact: Optional[str] = None
    cost: Optional[float] = None
    notes: Optional[str] = None


@app.get("/api/historical-records")
def list_historical(_u: dict = Depends(get_current_user)) -> dict:
    return {"success": True, "records": _list("historical_records")}


@app.post("/api/historical-records")
def create_historical(
    data: HistoricalIn, _u: dict = Depends(get_current_user)
) -> dict:
    row = _insert("historical_records", data.model_dump(exclude_none=True))
    return {"success": True, "record": row}


@app.put("/api/historical-records/{record_id}")
def update_historical(
    record_id: str,
    work_date: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    contractor_name: Optional[str] = Query(None),
    contractor_contact: Optional[str] = Query(None),
    cost: Optional[float] = Query(None),
    notes: Optional[str] = Query(None),
    _u: dict = Depends(get_current_user),
) -> dict:
    data = {
        "work_date": work_date, "scope": scope, "category": category,
        "description": description, "location": location,
        "contractor_name": contractor_name,
        "contractor_contact": contractor_contact, "cost": cost, "notes": notes,
    }
    row = _update("historical_records", record_id, data)
    return {"success": True, "record": row}


@app.delete("/api/historical-records/{record_id}")
def delete_historical(
    record_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    _delete("historical_records", record_id)
    return {"success": True}


# --- Analytics --------------------------------------------------------------

@app.get("/api/analytics/costs")
def analytics_costs(
    _u: dict = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    with closing(db()) as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(cost),0) total, COUNT(*) c FROM maintenance_requests"
        ).fetchone()
        by_month = conn.execute(
            "SELECT substr(created_at,1,7) AS month, COALESCE(SUM(cost),0) total, COUNT(*) c "
            "FROM maintenance_requests GROUP BY month ORDER BY month DESC LIMIT 12"
        ).fetchall()
        by_category = conn.execute(
            "SELECT COALESCE(category,'general') category, COALESCE(SUM(cost),0) total, COUNT(*) c "
            "FROM maintenance_requests GROUP BY category ORDER BY total DESC"
        ).fetchall()
        by_location = conn.execute(
            "SELECT COALESCE(location_type,'unknown') location_type, "
            "COALESCE(SUM(cost),0) total, COUNT(*) c "
            "FROM maintenance_requests GROUP BY location_type"
        ).fetchall()
    return {
        "total_cost": total["total"] or 0,
        "total_requests": total["c"],
        "costs_by_month": [dict(r) for r in by_month],
        "costs_by_category": [dict(r) for r in by_category],
        "costs_by_location": [dict(r) for r in by_location],
        "costs_by_apartment": [],
    }


@app.get("/api/analytics/yearly-summary")
def yearly_summary(_u: dict = Depends(get_current_user)) -> dict:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT substr(created_at,1,4) year, COUNT(*) total_requests, "
            "COALESCE(SUM(cost),0) total_cost "
            "FROM maintenance_requests GROUP BY year ORDER BY year DESC"
        ).fetchall()
    return [
        {"year": r["year"], "total_requests": r["total_requests"],
         "total_cost": r["total_cost"] or 0}
        for r in rows
    ]


@app.get("/api/analytics/apartment/{apartment_id}")
def analytics_apartment(
    apartment_id: str, _u: dict = Depends(get_current_user)
) -> dict:
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) total_requests, COALESCE(SUM(cost),0) total_cost "
            "FROM maintenance_requests WHERE CAST(location_id AS TEXT)=? AND location_type='apartment'",
            (str(apartment_id),),
        ).fetchone()
        recent = conn.execute(
            "SELECT * FROM maintenance_requests "
            "WHERE CAST(location_id AS TEXT)=? AND location_type='apartment' "
            "ORDER BY created_at DESC LIMIT 10",
            (str(apartment_id),),
        ).fetchall()
    return {
        "apartment_id": apartment_id,
        "total_requests": row["total_requests"],
        "total_cost": row["total_cost"] or 0,
        "recent_requests": [dict(r) for r in recent],
    }


# --- Log unknown API calls ---------------------------------------------------

@app.middleware("http")
async def log_unhandled(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404 and request.url.path.startswith("/api/"):
        print(f"[404] {request.method} {request.url.path}")
    return response
