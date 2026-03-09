#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import os
import re
import sqlite3
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cafeteria.db"
DEFAULT_BACKUP_DIR = ROOT_DIR / "backups"

DB_PATH = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(DEFAULT_BACKUP_DIR)))
DEFAULT_APP_FILE = ROOT_DIR / "Input" / "cafeteria_v2.html"

WRITE_LOCK = threading.Lock()
ENABLE_HOURLY_BACKUP = True
AUTH_USER = os.getenv("BASIC_AUTH_USER", "")
AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Monterrey")


PRODUCTS = {
    1: {"name": "Torta de arrachera", "price": 60.0},
    2: {"name": "Torta de jamón", "price": 60.0},
    3: {"name": "Torta de pechuga de pavo", "price": 60.0},
    4: {"name": "Torta de huevo", "price": 60.0},
    5: {"name": "Torta de pollo deshebrado", "price": 60.0},
    6: {"name": "Torta de pollo (con mayonesa)", "price": 55.0},
    7: {"name": "Gringa de arrachera", "price": 50.0},
    8: {"name": "Sincronizada de jamón / pechuga de pavo", "price": 45.0},
    9: {"name": "Sándwich de pollo deshebrado", "price": 45.0},
    10: {"name": "Tostada de pollo", "price": 50.0},
    11: {"name": "Tacos dorados de pollo (3 tacos)", "price": 45.0},
    12: {"name": "Taco dorado de pollo (unitario)", "price": 18.0},
    13: {"name": "Chilaquiles con pollo", "price": 55.0},
    14: {"name": "Chilaquiles sencillos (sin pollo)", "price": 45.0},
    15: {"name": "Spaghetti a la boloñesa", "price": 55.0},
    16: {"name": "Pan pita con carne", "price": 70.0},
    17: {"name": "Pan pita con pollo", "price": 70.0},
    18: {"name": "Bolipizza", "price": 50.0},
    19: {"name": "Vaso de verduras (pepino, zanahoria, jícama)", "price": 18.0},
    20: {"name": "Bolsa de palomitas", "price": 15.0},
    21: {"name": "Bolsa de cacahuate natural", "price": 15.0},
    22: {"name": "Bolsa de cacahuate en cáscara", "price": 8.0},
    23: {"name": "Panqué de cocoa", "price": 20.0},
    24: {"name": "Cupcake de vainilla", "price": 20.0},
    25: {"name": "Cupcake de frutos rojos", "price": 20.0},
    26: {"name": "Barrita de amaranto", "price": 15.0},
    27: {"name": "Palanqueta", "price": 12.0},
    28: {"name": "Habas enchiladas", "price": 15.0},
    29: {"name": "Garbanzos enchilados", "price": 15.0},
    30: {"name": "Maicitos enchilados", "price": 15.0},
    31: {"name": "Barra de granola", "price": 20.0},
    32: {"name": "Leche Santa Clara fresa", "price": 20.0},
    33: {"name": "Leche Santa Clara chocolate", "price": 20.0},
    34: {"name": "Congelada / boli de jugo natural", "price": 20.0},
    35: {"name": "Jugo natural tetra pack", "price": 18.0},
    36: {"name": "Botella de agua natural (½ litro)", "price": 10.0},
    37: {"name": "Botella de agua natural (1 litro)", "price": 18.0},
    38: {"name": "Botella de agua de sabor (½ litro)", "price": 16.0},
    39: {"name": "Botella de agua de sabor (1 litro)", "price": 24.0},
}


DEFAULT_STUDENTS = [
    {"name": "Sofía García", "grade": "3°A", "emoji": "👧", "paymentType": "transfer", "familyId": "FAM-001", "initialBalance": 200.0},
    {"name": "Mateo García", "grade": "5°B", "emoji": "👦", "paymentType": "transfer", "familyId": "FAM-001", "initialBalance": 0.0},
    {"name": "Valentina Hernández", "grade": "4°A", "emoji": "👧", "paymentType": "cole", "familyId": None, "initialBalance": -120.0},
    {"name": "Santiago Martínez", "grade": "4°A", "emoji": "👦", "paymentType": "transfer", "familyId": "FAM-002", "initialBalance": 0.0},
    {"name": "Regina Martínez", "grade": "6°A", "emoji": "👧", "paymentType": "transfer", "familyId": "FAM-002", "initialBalance": -55.0},
    {"name": "Emiliano Torres", "grade": "5°A", "emoji": "👦", "paymentType": "cole", "familyId": None, "initialBalance": 300.0},
    {"name": "Camila Flores", "grade": "5°A", "emoji": "👧", "paymentType": "transfer", "familyId": None, "initialBalance": -230.0},
    {"name": "Leonardo Ramírez", "grade": "5°B", "emoji": "👦", "paymentType": "cole", "familyId": "FAM-003", "initialBalance": 0.0},
    {"name": "Isabella Ramírez", "grade": "3°A", "emoji": "👧", "paymentType": "cole", "familyId": "FAM-003", "initialBalance": -45.0},
    {"name": "Diego Morales", "grade": "6°B", "emoji": "👦", "paymentType": "transfer", "familyId": None, "initialBalance": 500.0},
]


def app_now() -> dt.datetime:
    try:
        return dt.datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def local_date() -> str:
    return app_now().date().isoformat()


def local_time() -> str:
    return app_now().strftime("%H:%M")


def db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = FULL;")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                grade TEXT NOT NULL,
                emoji TEXT NOT NULL DEFAULT '👦',
                payment_type TEXT NOT NULL CHECK (payment_type IN ('transfer', 'cole')),
                family_id TEXT,
                initial_balance REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                order_time TEXT NOT NULL,
                total REAL NOT NULL CHECK (total >= 0),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                qty INTEGER NOT NULL CHECK (qty > 0),
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_key TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                payment_date TEXT NOT NULL,
                method TEXT NOT NULL CHECK (method IN ('transfer', 'efectivo')),
                note TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_orders_student_date ON orders(student_id, order_date);
            CREATE INDEX IF NOT EXISTS idx_payments_family_date ON payments(family_key, payment_date);
            """
        )

        count = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO students (name, grade, emoji, payment_type, family_id, initial_balance)
                VALUES (:name, :grade, :emoji, :paymentType, :familyId, :initialBalance)
                """,
                DEFAULT_STUDENTS,
            )
        conn.commit()


def maybe_hourly_backup() -> None:
    if not ENABLE_HOURLY_BACKUP or not DB_PATH.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    hour_key = app_now().strftime("%Y%m%d_%H")
    backup_path = BACKUP_DIR / f"cafeteria_{hour_key}.db"
    if backup_path.exists():
        return

    with sqlite3.connect(DB_PATH) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)

    backups = sorted(BACKUP_DIR.glob("cafeteria_*.db"))
    if len(backups) > 168:
        for old in backups[:-168]:
            old.unlink(missing_ok=True)


def force_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = app_now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"cafeteria_manual_{stamp}.db"
    with sqlite3.connect(DB_PATH) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)
    return backup_path


def row_to_student(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "grade": row["grade"],
        "emoji": row["emoji"],
        "paymentType": row["payment_type"],
        "familyId": row["family_id"],
        "initialBalance": float(row["initial_balance"]),
    }


def row_to_payment(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "familyKey": row["family_key"],
        "amount": float(row["amount"]),
        "date": row["payment_date"],
        "method": row["method"],
        "note": row["note"],
    }


def fetch_students(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        """
        SELECT id, name, grade, emoji, payment_type, family_id, initial_balance
        FROM students
        ORDER BY id
        """
    ).fetchall()
    return [row_to_student(r) for r in rows]


def fetch_payments(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        """
        SELECT id, family_key, amount, payment_date, method, note
        FROM payments
        ORDER BY payment_date ASC, id ASC
        """
    ).fetchall()
    return [row_to_payment(r) for r in rows]


def fetch_orders(conn: sqlite3.Connection) -> list:
    orders_rows = conn.execute(
        """
        SELECT id, student_id, order_date, order_time, total
        FROM orders
        ORDER BY order_date ASC, id ASC
        """
    ).fetchall()

    orders = []
    if not orders_rows:
        return orders

    order_ids = [r["id"] for r in orders_rows]
    placeholders = ",".join(["?"] * len(order_ids))
    item_rows = conn.execute(
        f"""
        SELECT order_id, product_id, qty, unit_price
        FROM order_items
        WHERE order_id IN ({placeholders})
        ORDER BY id ASC
        """,
        order_ids,
    ).fetchall()

    items_by_order = {}
    for item in item_rows:
        items_by_order.setdefault(item["order_id"], []).append(
            {
                "productId": item["product_id"],
                "qty": item["qty"],
                "unitPrice": float(item["unit_price"]),
            }
        )

    for row in orders_rows:
        orders.append(
            {
                "id": row["id"],
                "studentId": row["student_id"],
                "date": row["order_date"],
                "time": row["order_time"],
                "items": items_by_order.get(row["id"], []),
                "total": float(row["total"]),
            }
        )
    return orders


def parse_json(body: bytes) -> dict:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    raise ValueError("JSON inválido.")


def validate_iso_date(value: str, field_name: str) -> str:
    try:
        dt.date.fromisoformat(value)
        return value
    except Exception:
        raise ValueError(f"{field_name} inválida. Usa formato YYYY-MM-DD.")


def validate_time_hhmm(value: str, field_name: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError(f"{field_name} inválida. Usa formato HH:MM.")
    return value


def normalize_cart(cart: list) -> tuple[list, float]:
    if not isinstance(cart, list) or len(cart) == 0:
        raise ValueError("El carrito está vacío.")

    normalized_items = []
    total = 0.0
    for item in cart:
        if not isinstance(item, dict):
            raise ValueError("Item inválido en carrito.")
        product_id = item.get("productId")
        qty = item.get("qty")
        if not isinstance(product_id, int) or product_id not in PRODUCTS:
            raise ValueError(f"Producto inválido: {product_id}")
        if not isinstance(qty, int) or qty <= 0:
            raise ValueError("Cantidad inválida.")
        unit_price = float(PRODUCTS[product_id]["price"])
        normalized_items.append({"productId": product_id, "qty": qty, "unitPrice": unit_price})
        total += unit_price * qty

    return normalized_items, round(total, 2)


def student_family_key(student_id: int, family_id: Optional[str]) -> str:
    return family_id or f"ind-{student_id}"


class CafeteriaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def send_json(self, status_code: int, payload: dict) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""
        return parse_json(raw)

    def is_authorized(self) -> bool:
        if not AUTH_USER or not AUTH_PASS:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        token = auth_header.split(" ", 1)[1].strip()
        try:
            decoded = base64.b64decode(token).decode("utf-8")
        except Exception:
            return False
        user, sep, pwd = decoded.partition(":")
        if not sep:
            return False
        return user == AUTH_USER and pwd == AUTH_PASS

    def require_auth(self) -> bool:
        if self.is_authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Cafeteria Escolar"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Auth required")
        return False

    def do_GET(self):
        if not self.require_auth():
            return
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            if DEFAULT_APP_FILE.exists():
                self.path = str(DEFAULT_APP_FILE.relative_to(ROOT_DIR))
                return super().do_GET()
            self.send_json(500, {"error": "No se encontró Input/cafeteria_v2.html"})
            return

        if parsed.path == "/api/health":
            self.send_json(200, {"ok": True, "date": local_date(), "timezone": APP_TIMEZONE})
            return

        if parsed.path == "/api/state":
            with db_connection() as conn:
                data = {
                    "students": fetch_students(conn),
                    "orders": fetch_orders(conn),
                    "payments": fetch_payments(conn),
                }
            self.send_json(200, data)
            return

        return super().do_GET()

    def do_POST(self):
        if not self.require_auth():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/orders":
                return self.handle_create_order()
            if parsed.path == "/api/students":
                return self.handle_create_student()
            if parsed.path == "/api/payments":
                return self.handle_create_payment()
            self.send_json(404, {"error": "Ruta no encontrada."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except sqlite3.IntegrityError as exc:
            self.send_json(400, {"error": f"Error de integridad de datos: {exc}"})
        except Exception:
            self.send_json(500, {"error": "Error interno del servidor."})

    def do_PUT(self):
        if not self.require_auth():
            return
        parsed = urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/orders/(\d+)", parsed.path)
            if match:
                order_id = int(match.group(1))
                return self.handle_update_order(order_id)

            match = re.fullmatch(r"/api/students/(\d+)", parsed.path)
            if match:
                student_id = int(match.group(1))
                return self.handle_update_student(student_id)

            self.send_json(404, {"error": "Ruta no encontrada."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except sqlite3.IntegrityError as exc:
            self.send_json(400, {"error": f"Error de integridad de datos: {exc}"})
        except Exception:
            self.send_json(500, {"error": "Error interno del servidor."})

    def do_DELETE(self):
        if not self.require_auth():
            return
        parsed = urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/orders/(\d+)", parsed.path)
            if match:
                order_id = int(match.group(1))
                return self.handle_delete_order(order_id)

            match = re.fullmatch(r"/api/students/(\d+)", parsed.path)
            if match:
                student_id = int(match.group(1))
                query = parse_qs(parsed.query or "")
                reassign_to_raw = query.get("reassignTo", [None])[0]
                purge_orders_raw = str(query.get("purgeOrders", ["0"])[0]).strip().lower()
                purge_orders = purge_orders_raw in {"1", "true", "yes", "y"}
                reassign_to = None
                if reassign_to_raw is not None and str(reassign_to_raw).strip():
                    reassign_to = int(str(reassign_to_raw).strip())
                return self.handle_delete_student(student_id, reassign_to=reassign_to, purge_orders=purge_orders)

            self.send_json(404, {"error": "Ruta no encontrada."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "Error interno del servidor."})

    def handle_create_order(self):
        payload = self.read_json_body()
        student_id = payload.get("studentId")
        cart = payload.get("cart")
        requested_date = payload.get("date")
        requested_time = payload.get("time")

        if not isinstance(student_id, int) or student_id <= 0:
            raise ValueError("studentId inválido.")
        normalized_items, total = normalize_cart(cart)

        order_date = validate_iso_date(str(requested_date), "Fecha") if requested_date is not None else local_date()
        order_time = validate_time_hhmm(str(requested_time), "Hora") if requested_time is not None else local_time()

        with WRITE_LOCK:
            with db_connection() as conn:
                student_exists = conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone()
                if not student_exists:
                    raise ValueError("El alumno seleccionado no existe.")

                cur = conn.execute(
                    """
                    INSERT INTO orders (student_id, order_date, order_time, total)
                    VALUES (?, ?, ?, ?)
                    """,
                    (student_id, order_date, order_time, total),
                )
                order_id = cur.lastrowid
                conn.executemany(
                    """
                    INSERT INTO order_items (order_id, product_id, qty, unit_price)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(order_id, i["productId"], i["qty"], i["unitPrice"]) for i in normalized_items],
                )
                conn.commit()
            maybe_hourly_backup()

        self.send_json(
            201,
            {
                "id": order_id,
                "studentId": student_id,
                "date": order_date,
                "time": order_time,
                "items": normalized_items,
                "total": total,
            },
        )

    def handle_update_order(self, order_id: int):
        if order_id <= 0:
            raise ValueError("orderId inválido.")

        payload = self.read_json_body()
        if not isinstance(payload, dict) or len(payload) == 0:
            raise ValueError("Se requiere al menos un campo para editar el pedido.")

        with WRITE_LOCK:
            with db_connection() as conn:
                current_order = conn.execute(
                    """
                    SELECT id, student_id, order_date, order_time, total
                    FROM orders
                    WHERE id = ?
                    """,
                    (order_id,),
                ).fetchone()
                if not current_order:
                    self.send_json(404, {"error": "Pedido no encontrado."})
                    return

                student_id = payload.get("studentId", current_order["student_id"])
                if not isinstance(student_id, int) or student_id <= 0:
                    raise ValueError("studentId inválido.")
                student_exists = conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone()
                if not student_exists:
                    raise ValueError("El alumno seleccionado no existe.")

                if "date" in payload:
                    order_date = validate_iso_date(str(payload.get("date")), "Fecha")
                else:
                    order_date = current_order["order_date"]

                if "time" in payload:
                    order_time = validate_time_hhmm(str(payload.get("time")), "Hora")
                else:
                    order_time = current_order["order_time"]

                if "cart" in payload:
                    normalized_items, total = normalize_cart(payload.get("cart"))
                    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
                    conn.executemany(
                        """
                        INSERT INTO order_items (order_id, product_id, qty, unit_price)
                        VALUES (?, ?, ?, ?)
                        """,
                        [(order_id, i["productId"], i["qty"], i["unitPrice"]) for i in normalized_items],
                    )
                else:
                    total = round(float(current_order["total"]), 2)
                    current_items = conn.execute(
                        """
                        SELECT product_id, qty, unit_price
                        FROM order_items
                        WHERE order_id = ?
                        ORDER BY id ASC
                        """,
                        (order_id,),
                    ).fetchall()
                    normalized_items = [
                        {"productId": r["product_id"], "qty": r["qty"], "unitPrice": float(r["unit_price"])}
                        for r in current_items
                    ]

                conn.execute(
                    """
                    UPDATE orders
                    SET student_id = ?, order_date = ?, order_time = ?, total = ?
                    WHERE id = ?
                    """,
                    (student_id, order_date, order_time, total, order_id),
                )
                conn.commit()
            maybe_hourly_backup()

        self.send_json(
            200,
            {
                "id": order_id,
                "studentId": student_id,
                "date": order_date,
                "time": order_time,
                "items": normalized_items,
                "total": total,
            },
        )

    def handle_delete_order(self, order_id: int):
        if order_id <= 0:
            raise ValueError("orderId inválido.")

        with WRITE_LOCK:
            with db_connection() as conn:
                cur = conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
                conn.commit()
                if cur.rowcount == 0:
                    self.send_json(404, {"error": "Pedido no encontrado."})
                    return
            maybe_hourly_backup()

        self.send_json(200, {"ok": True})

    def handle_create_student(self):
        payload = self.read_json_body()
        name = str(payload.get("name", "")).strip()
        grade = str(payload.get("grade", "")).strip()
        emoji = str(payload.get("emoji", "👦")).strip() or "👦"
        payment_type = str(payload.get("paymentType", "transfer")).strip()
        family_id = payload.get("familyId")
        initial_balance = payload.get("initialBalance", 0)

        if not name:
            raise ValueError("El nombre es obligatorio.")
        if not grade:
            raise ValueError("El grado es obligatorio.")
        if payment_type not in {"transfer", "cole"}:
            raise ValueError("Tipo de pago inválido.")
        if family_id is not None:
            family_id = str(family_id).strip() or None
        try:
            initial_balance = float(initial_balance)
        except (TypeError, ValueError):
            raise ValueError("Saldo inicial inválido.")

        with WRITE_LOCK:
            with db_connection() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO students (name, grade, emoji, payment_type, family_id, initial_balance)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, grade, emoji, payment_type, family_id, initial_balance),
                )
                student_id = cur.lastrowid
                conn.commit()
            maybe_hourly_backup()

        self.send_json(
            201,
            {
                "id": student_id,
                "name": name,
                "grade": grade,
                "emoji": emoji,
                "paymentType": payment_type,
                "familyId": family_id,
                "initialBalance": round(initial_balance, 2),
            },
        )

    def handle_update_student(self, student_id: int):
        if student_id <= 0:
            raise ValueError("studentId inválido.")

        payload = self.read_json_body()
        if not isinstance(payload, dict) or len(payload) == 0:
            raise ValueError("Se requiere al menos un campo para editar el alumno.")

        with WRITE_LOCK:
            with db_connection() as conn:
                current = conn.execute(
                    """
                    SELECT id, name, grade, emoji, payment_type, family_id, initial_balance
                    FROM students
                    WHERE id = ?
                    """,
                    (student_id,),
                ).fetchone()
                if not current:
                    self.send_json(404, {"error": "Alumno no encontrado."})
                    return

                old_family_id = current["family_id"]
                old_key = student_family_key(student_id, old_family_id)

                if "name" in payload:
                    name = str(payload.get("name", "")).strip()
                else:
                    name = current["name"]
                if not name:
                    raise ValueError("El nombre es obligatorio.")

                if "grade" in payload:
                    grade = str(payload.get("grade", "")).strip()
                else:
                    grade = current["grade"]
                if not grade:
                    raise ValueError("El grado es obligatorio.")

                if "emoji" in payload:
                    emoji = str(payload.get("emoji", "👦")).strip() or "👦"
                else:
                    emoji = current["emoji"]

                if "paymentType" in payload:
                    payment_type = str(payload.get("paymentType", "")).strip()
                else:
                    payment_type = current["payment_type"]
                if payment_type not in {"transfer", "cole"}:
                    raise ValueError("Tipo de pago inválido.")

                if "familyId" in payload:
                    family_id = payload.get("familyId")
                    if family_id is not None:
                        family_id = str(family_id).strip() or None
                else:
                    family_id = current["family_id"]

                if "initialBalance" in payload:
                    raw_initial_balance = payload.get("initialBalance", 0)
                    try:
                        initial_balance = float(raw_initial_balance)
                    except (TypeError, ValueError):
                        raise ValueError("Saldo inicial inválido.")
                else:
                    initial_balance = float(current["initial_balance"])

                conn.execute(
                    """
                    UPDATE students
                    SET name = ?, grade = ?, emoji = ?, payment_type = ?, family_id = ?, initial_balance = ?
                    WHERE id = ?
                    """,
                    (name, grade, emoji, payment_type, family_id, initial_balance, student_id),
                )

                new_key = student_family_key(student_id, family_id)
                if old_key != new_key:
                    # Safe migration: from individual key to any other key.
                    if old_family_id is None:
                        conn.execute(
                            """
                            UPDATE payments
                            SET family_key = ?
                            WHERE family_key = ?
                            """,
                            (new_key, old_key),
                        )
                    else:
                        other_members = conn.execute(
                            """
                            SELECT COUNT(*) AS c
                            FROM students
                            WHERE family_id = ? AND id != ?
                            """,
                            (old_family_id, student_id),
                        ).fetchone()["c"]
                        if other_members == 0:
                            conn.execute(
                                """
                                UPDATE payments
                                SET family_key = ?
                                WHERE family_key = ?
                                """,
                                (new_key, old_family_id),
                            )

                conn.commit()
            maybe_hourly_backup()

        self.send_json(
            200,
            {
                "id": student_id,
                "name": name,
                "grade": grade,
                "emoji": emoji,
                "paymentType": payment_type,
                "familyId": family_id,
                "initialBalance": round(initial_balance, 2),
            },
        )

    def handle_delete_student(self, student_id: int, reassign_to: Optional[int] = None, purge_orders: bool = False):
        if student_id <= 0:
            raise ValueError("studentId inválido.")
        if reassign_to is not None and reassign_to <= 0:
            raise ValueError("reassignTo inválido.")
        if reassign_to is not None and reassign_to == student_id:
            raise ValueError("No puedes reasignar al mismo alumno.")

        with WRITE_LOCK:
            with db_connection() as conn:
                source = conn.execute(
                    """
                    SELECT id, family_id
                    FROM students
                    WHERE id = ?
                    """,
                    (student_id,),
                ).fetchone()
                if not source:
                    self.send_json(404, {"error": "Alumno no encontrado."})
                    return

                target = None
                if reassign_to is not None:
                    target = conn.execute(
                        """
                        SELECT id, family_id
                        FROM students
                        WHERE id = ?
                        """,
                        (reassign_to,),
                    ).fetchone()
                    if not target:
                        raise ValueError("El alumno destino para reassignTo no existe.")

                source_key = student_family_key(student_id, source["family_id"])
                orders_count = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM orders
                    WHERE student_id = ?
                    """,
                    (student_id,),
                ).fetchone()["c"]
                payments_count = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM payments
                    WHERE family_key = ?
                    """,
                    (source_key,),
                ).fetchone()["c"]

                if orders_count > 0:
                    if target is not None:
                        conn.execute(
                            """
                            UPDATE orders
                            SET student_id = ?
                            WHERE student_id = ?
                            """,
                            (target["id"], student_id),
                        )
                    elif purge_orders:
                        conn.execute(
                            """
                            DELETE FROM orders
                            WHERE student_id = ?
                            """,
                            (student_id,),
                        )
                    else:
                        raise ValueError(
                            f"El alumno tiene {orders_count} pedido(s). Usa reassignTo=<id> o purgeOrders=1 para eliminar."
                        )

                if payments_count > 0 and source["family_id"] is None:
                    if target is not None:
                        target_key = student_family_key(target["id"], target["family_id"])
                        conn.execute(
                            """
                            UPDATE payments
                            SET family_key = ?
                            WHERE family_key = ?
                            """,
                            (target_key, source_key),
                        )
                    elif purge_orders:
                        conn.execute(
                            """
                            DELETE FROM payments
                            WHERE family_key = ?
                            """,
                            (source_key,),
                        )
                    else:
                        raise ValueError(
                            f"El alumno tiene {payments_count} pago(s) individuales. Usa reassignTo=<id> o purgeOrders=1."
                        )

                conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
                conn.commit()
            maybe_hourly_backup()

        self.send_json(200, {"ok": True})

    def handle_create_payment(self):
        payload = self.read_json_body()
        family_key = str(payload.get("familyKey", "")).strip()
        method = str(payload.get("method", "transfer")).strip()
        note = payload.get("note")
        amount = payload.get("amount", 0)
        requested_date = payload.get("date")

        if not family_key:
            raise ValueError("familyKey es obligatorio.")
        if method not in {"transfer", "efectivo"}:
            raise ValueError("Método de pago inválido.")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise ValueError("Monto inválido.")
        if amount <= 0:
            raise ValueError("El monto debe ser mayor a 0.")

        if note is not None:
            note = str(note).strip() or None

        payment_date = validate_iso_date(str(requested_date), "Fecha") if requested_date is not None else local_date()
        with WRITE_LOCK:
            with db_connection() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO payments (family_key, amount, payment_date, method, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (family_key, amount, payment_date, method, note),
                )
                payment_id = cur.lastrowid
                conn.commit()
            maybe_hourly_backup()

        self.send_json(
            201,
            {
                "id": payment_id,
                "familyKey": family_key,
                "amount": round(amount, 2),
                "date": payment_date,
                "method": method,
                "note": note,
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cafetería Escolar - servidor simple de producción")
    parser.add_argument("--host", default="0.0.0.0", help="Host para levantar el servidor")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")), help="Puerto para levantar el servidor")
    parser.add_argument("--db-path", default=str(DB_PATH), help="Ruta del archivo SQLite")
    parser.add_argument("--backup-dir", default=str(BACKUP_DIR), help="Carpeta para backups")
    parser.add_argument("--basic-user", default=AUTH_USER, help="Usuario para Basic Auth (opcional)")
    parser.add_argument("--basic-pass", default=AUTH_PASS, help="Password para Basic Auth (opcional)")
    parser.add_argument("--no-hourly-backup", action="store_true", help="Desactiva el backup automático por hora")
    parser.add_argument("--backup-now", action="store_true", help="Solo genera un backup manual y termina")
    return parser.parse_args()


def main() -> None:
    global ENABLE_HOURLY_BACKUP, DB_PATH, BACKUP_DIR, AUTH_USER, AUTH_PASS
    args = parse_args()
    ENABLE_HOURLY_BACKUP = not args.no_hourly_backup
    DB_PATH = Path(args.db_path)
    BACKUP_DIR = Path(args.backup_dir)
    AUTH_USER = args.basic_user.strip()
    AUTH_PASS = args.basic_pass.strip()
    if not DB_PATH.is_absolute():
        DB_PATH = ROOT_DIR / DB_PATH
    if not BACKUP_DIR.is_absolute():
        BACKUP_DIR = ROOT_DIR / BACKUP_DIR

    init_db()

    if args.backup_now:
        backup_path = force_backup()
        print(f"Backup creado: {backup_path}")
        return

    server = ThreadingHTTPServer((args.host, args.port), CafeteriaHandler)
    print(f"Cafetería lista en http://{args.host}:{args.port}")
    print("Presiona Ctrl+C para detener.")
    server.serve_forever()


if __name__ == "__main__":
    main()
