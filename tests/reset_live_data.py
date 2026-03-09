#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def make_headers(user: str, password: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"
    return headers


def call(base: str, headers: dict, method: str, path: str, payload=None, retries: int = 6):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    last_error = None
    for attempt in range(retries):
        req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code in {502, 503, 504} and attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
                last_error = f"HTTP {exc.code} {method} {path}: {raw}"
                continue
            try:
                parsed = json.loads(raw)
                message = parsed.get("error") or raw
            except Exception:
                message = raw
            raise RuntimeError(f"HTTP {exc.code} {method} {path}: {message}") from exc
        except urllib.error.URLError as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise RuntimeError(f"URL error {method} {path}: {last_error}") from exc
    raise RuntimeError(f"Request failed {method} {path}: {last_error}")


def main():
    parser = argparse.ArgumentParser(description="Limpia todos los datos de producción (students/orders/payments)")
    parser.add_argument("--base-url", required=True, help="Ej: https://lecantine-production.up.railway.app")
    parser.add_argument("--user", default="", help="Basic auth user")
    parser.add_argument("--password", default="", help="Basic auth password")
    parser.add_argument("--snapshot-dir", default="backups/reset_snapshots", help="Carpeta local para snapshot previo")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    headers = make_headers(args.user, args.password)
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    print("1) Leyendo estado actual...")
    state = call(base, headers, "GET", "/api/state")
    students = state.get("students", [])
    orders = state.get("orders", [])
    payments = state.get("payments", [])
    print(f"   students={len(students)} orders={len(orders)} payments={len(payments)}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = snapshot_dir / f"pre_reset_{stamp}.json"
    snapshot_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"2) Snapshot guardado: {snapshot_path}")

    print("3) Eliminando pagos...")
    for p in payments:
        call(base, headers, "DELETE", f"/api/payments/{p['id']}")
    print(f"   pagos eliminados={len(payments)}")

    print("4) Eliminando pedidos...")
    for o in orders:
        call(base, headers, "DELETE", f"/api/orders/{o['id']}")
    print(f"   pedidos eliminados={len(orders)}")

    print("5) Eliminando alumnos...")
    deleted_students = 0
    for s in students:
        try:
            call(base, headers, "DELETE", f"/api/students/{s['id']}")
        except RuntimeError:
            # Fallback defensivo por si queda algún dato ligado inesperado.
            call(base, headers, "DELETE", f"/api/students/{s['id']}?purgeOrders=1")
        deleted_students += 1
    print(f"   alumnos eliminados={deleted_students}")

    print("6) Verificación final...")
    final_state = call(base, headers, "GET", "/api/state")
    fs = len(final_state.get("students", []))
    fo = len(final_state.get("orders", []))
    fp = len(final_state.get("payments", []))
    print(f"   students={fs} orders={fo} payments={fp}")

    if fs != 0 or fo != 0 or fp != 0:
        raise RuntimeError("Reset incompleto: aún hay datos.")

    print("RESULT: PASS (base limpia para arranque en cero)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr)
        sys.exit(1)
