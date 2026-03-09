#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import random
import sys
import urllib.error
import urllib.parse
import urllib.request


def make_headers(user: str, password: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"
    return headers


def call_json(base_url: str, headers: dict, method: str, path: str, payload=None):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base_url + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
            message = parsed.get("error") or raw
        except Exception:
            message = raw
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {message}") from exc


def call_text(base_url: str, headers: dict, method: str, path: str) -> str:
    req = urllib.request.Request(base_url + path, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {raw}") from exc


def main():
    parser = argparse.ArgumentParser(description="Smoke test operativo para Lecantine en producción")
    parser.add_argument("--base-url", required=True, help="Ej: https://lecantine-production.up.railway.app")
    parser.add_argument("--user", default="", help="Basic auth user")
    parser.add_argument("--password", default="", help="Basic auth password")
    parser.add_argument("--seed", type=int, default=20260309)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    headers = make_headers(args.user, args.password)
    rng = random.Random(args.seed)

    print("1) Health check")
    health = call_json(base_url, headers, "GET", "/api/health")
    if not health.get("ok"):
        raise RuntimeError("Health check sin ok=true")
    today = health["date"]
    print(f"   ok date={today} timezone={health.get('timezone')}")

    print("2) Leer estado")
    state = call_json(base_url, headers, "GET", "/api/state")
    print(f"   students={len(state.get('students', []))} orders={len(state.get('orders', []))} payments={len(state.get('payments', []))}")

    suffix = f"{today.replace('-', '')}-{rng.randint(1000, 9999)}"
    created_student = None
    created_order = None
    created_payment = None

    try:
        print("3) Alta alumno")
        created_student = call_json(
            base_url,
            headers,
            "POST",
            "/api/students",
            {
                "name": f"Smoke Alumno {suffix}",
                "grade": "SMK",
                "emoji": "🧒",
                "paymentType": "cole",
                "familyId": None,
                "initialBalance": 0,
            },
        )
        print(f"   student_id={created_student['id']}")

        print("4) Crear + editar pedido")
        created_order = call_json(
            base_url,
            headers,
            "POST",
            "/api/orders",
            {"studentId": created_student["id"], "cart": [{"productId": 1, "qty": 1}]},
        )
        updated_order = call_json(
            base_url,
            headers,
            "PUT",
            f"/api/orders/{created_order['id']}",
            {
                "studentId": created_student["id"],
                "cart": [{"productId": 20, "qty": 2}],
                "date": today,
                "time": "10:10",
            },
        )
        print(f"   order_id={updated_order['id']} total={updated_order['total']}")

        print("5) Crear + editar pago")
        created_payment = call_json(
            base_url,
            headers,
            "POST",
            "/api/payments",
            {
                "familyKey": f"ind-{created_student['id']}",
                "amount": 50,
                "method": "efectivo",
                "note": "smoke create",
                "date": today,
            },
        )
        updated_payment = call_json(
            base_url,
            headers,
            "PUT",
            f"/api/payments/{created_payment['id']}",
            {
                "familyKey": f"ind-{created_student['id']}",
                "amount": 60,
                "method": "transfer",
                "note": "smoke update",
                "date": today,
            },
        )
        print(f"   payment_id={updated_payment['id']} amount={updated_payment['amount']}")

        print("6) Export CSV")
        query = urllib.parse.urlencode({"start": today, "end": today, "paymentType": "cole"})
        csv_text = call_text(base_url, headers, "GET", f"/api/export.csv?{query}")
        if "family_key" not in csv_text:
            raise RuntimeError("CSV no contiene encabezado esperado")
        print(f"   csv_ok chars={len(csv_text)}")

        print("7) Limpieza (delete pago, pedido, alumno)")
        call_json(base_url, headers, "DELETE", f"/api/payments/{created_payment['id']}")
        created_payment = None
        call_json(base_url, headers, "DELETE", f"/api/orders/{created_order['id']}")
        created_order = None
        call_json(base_url, headers, "DELETE", f"/api/students/{created_student['id']}")
        created_student = None
        print("   cleanup_ok")

    finally:
        # Best-effort cleanup if anything failed in the middle.
        try:
            if created_payment:
                call_json(base_url, headers, "DELETE", f"/api/payments/{created_payment['id']}")
        except Exception:
            pass
        try:
            if created_order:
                call_json(base_url, headers, "DELETE", f"/api/orders/{created_order['id']}")
        except Exception:
            pass
        try:
            if created_student:
                call_json(base_url, headers, "DELETE", f"/api/students/{created_student['id']}?purgeOrders=1")
        except Exception:
            pass

    print("RESULT: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr)
        sys.exit(1)
