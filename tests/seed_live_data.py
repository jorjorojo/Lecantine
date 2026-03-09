#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import random
import sys
import urllib.request
from zoneinfo import ZoneInfo

PRODUCT_IDS = list(range(1, 40))
TZ = ZoneInfo("America/Monterrey")


def make_headers(user: str, password: str):
    headers = {"Content-Type": "application/json"}
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers


def call(base: str, headers: dict, method: str, path: str, payload=None):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def random_cart(rng: random.Random):
    size = rng.randint(1, 4)
    ids = rng.sample(PRODUCT_IDS, size)
    return [{"productId": pid, "qty": rng.randint(1, 3)} for pid in ids]


def family_key(student):
    return student.get("familyId") or f"ind-{student['id']}"


def random_time(rng: random.Random):
    h = rng.randint(8, 15)
    m = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
    return f"{h:02d}:{m:02d}"


def main():
    parser = argparse.ArgumentParser(description="Puebla datos simulados en el servicio en línea")
    parser.add_argument("--base-url", required=True, help="Ej: https://lecantine-production.up.railway.app")
    parser.add_argument("--user", default="", help="Basic auth user")
    parser.add_argument("--password", default="", help="Basic auth password")
    parser.add_argument("--days", type=int, default=7, help="Días hacia atrás incluyendo hoy")
    parser.add_argument("--orders-per-day-min", type=int, default=18)
    parser.add_argument("--orders-per-day-max", type=int, default=32)
    parser.add_argument("--payments-probability", type=float, default=0.22)
    parser.add_argument("--seed", type=int, default=20260309)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    headers = make_headers(args.user, args.password)
    rng = random.Random(args.seed)

    state = call(base, headers, "GET", "/api/state")
    students = state["students"]
    if not students:
        print("No hay alumnos para poblar pedidos.", file=sys.stderr)
        sys.exit(1)

    created_orders = 0
    created_payments = 0

    for day_offset in range(args.days - 1, -1, -1):
        day = (dt.datetime.now(TZ).date() - dt.timedelta(days=day_offset)).isoformat()
        orders_today = rng.randint(args.orders_per_day_min, args.orders_per_day_max)

        for _ in range(orders_today):
            student = rng.choice(students)
            payload = {
                "studentId": student["id"],
                "cart": random_cart(rng),
                "date": day,
                "time": random_time(rng),
            }
            call(base, headers, "POST", "/api/orders", payload)
            created_orders += 1

            if rng.random() < args.payments_probability:
                pay = {
                    "familyKey": family_key(student),
                    "amount": round(rng.uniform(40, 380), 2),
                    "method": "transfer" if rng.random() < 0.72 else "efectivo",
                    "note": "Simulación",
                    "date": day,
                }
                call(base, headers, "POST", "/api/payments", pay)
                created_payments += 1

    final_state = call(base, headers, "GET", "/api/state")
    print("SEED_RESULT")
    print(f"created_orders={created_orders}")
    print(f"created_payments={created_payments}")
    print(f"final_students={len(final_state['students'])}")
    print(f"final_orders={len(final_state['orders'])}")
    print(f"final_payments={len(final_state['payments'])}")


if __name__ == "__main__":
    main()
