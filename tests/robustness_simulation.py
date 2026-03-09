#!/usr/bin/env python3
import argparse
import json
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PRODUCT_IDS = list(range(1, 40))


def request_json(base_url: str, method: str, path: str, payload=None, timeout=20, retries=3):
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url=f"{base_url}{path}",
                data=body,
                method=method,
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"Request failed {method} {path}: {last_exc}")


def wait_for_health(base_url: str, timeout_s: int = 15):
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            data = request_json(base_url, "GET", "/api/health", None, timeout=2)
            if data.get("ok"):
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("El servidor no respondió en /api/health")


def family_key(student: dict) -> str:
    return student["familyId"] or f"ind-{student['id']}"


def random_cart(rng: random.Random) -> list:
    size = rng.randint(1, 4)
    product_ids = rng.sample(PRODUCT_IDS, size)
    return [{"productId": pid, "qty": rng.randint(1, 3)} for pid in product_ids]


def validate_state(state: dict):
    students = state["students"]
    orders = state["orders"]
    payments = state["payments"]
    student_ids = {s["id"] for s in students}

    for o in orders:
        assert o["studentId"] in student_ids, f"Order with unknown studentId={o['studentId']}"
        calc = round(sum((i["qty"] * i["unitPrice"]) for i in o["items"]), 2)
        total = round(o["total"], 2)
        assert calc == total, f"Order total mismatch id={o['id']}: {calc} != {total}"
        for i in o["items"]:
            assert i["productId"] in PRODUCT_IDS, f"Invalid product id={i['productId']}"
            assert i["qty"] > 0, "qty must be > 0"
            assert i["unitPrice"] >= 0, "unitPrice must be >= 0"

    for p in payments:
        assert p["amount"] > 0, "payment amount must be > 0"
        assert p["method"] in ("transfer", "efectivo"), f"invalid payment method={p['method']}"


def run_vertical_flow(base_url: str):
    health = request_json(base_url, "GET", "/api/health")
    state = request_json(base_url, "GET", "/api/state")
    initial_students = len(state["students"])

    new_student = request_json(
        base_url,
        "POST",
        "/api/students",
        {
            "name": "Alumno Prueba",
            "grade": "2°B",
            "emoji": "🧒",
            "paymentType": "cole",
            "familyId": None,
            "initialBalance": 0,
        },
    )
    assert new_student["id"] > 0, "No se creó alumno"

    new_order = request_json(
        base_url,
        "POST",
        "/api/orders",
        {
            "studentId": new_student["id"],
            "cart": [{"productId": 1, "qty": 2}, {"productId": 20, "qty": 1}],
        },
    )
    assert new_order["id"] > 0, "No se creó pedido"
    assert new_order["date"] == health["date"], "El pedido no cae en la fecha operativa actual (timezone mismatch)"
    updated_order = request_json(
        base_url,
        "PUT",
        f"/api/orders/{new_order['id']}",
        {
            "studentId": new_student["id"],
            "cart": [{"productId": 1, "qty": 1}, {"productId": 37, "qty": 1}],
            "time": "10:20",
        },
    )
    assert updated_order["id"] == new_order["id"], "No se actualizó pedido"
    assert round(updated_order["total"], 2) == 78.0, "Total de pedido editado inválido"

    updated_student = request_json(
        base_url,
        "PUT",
        f"/api/students/{new_student['id']}",
        {
            "name": "Alumno Prueba Editado",
            "grade": "2°B",
            "emoji": "🧒",
            "paymentType": "cole",
            "familyId": None,
            "initialBalance": 15,
        },
    )
    assert updated_student["name"] == "Alumno Prueba Editado", "No se actualizó alumno"
    assert round(updated_student["initialBalance"], 2) == 15.0, "Saldo inicial editado inválido"

    payment = request_json(
        base_url,
        "POST",
        "/api/payments",
        {
            "familyKey": f"ind-{new_student['id']}",
            "amount": 120,
            "method": "efectivo",
            "note": "Pago prueba",
        },
    )
    assert payment["id"] > 0, "No se creó pago"

    deleted = request_json(base_url, "DELETE", f"/api/orders/{new_order['id']}")
    assert deleted.get("ok") is True, "No se eliminó pedido"

    state2 = request_json(base_url, "GET", "/api/state")
    assert len(state2["students"]) == initial_students + 1, "No persistió alta de alumno"
    assert not any(o["id"] == new_order["id"] for o in state2["orders"]), "Pedido eliminado sigue presente"
    assert any(p["id"] == payment["id"] for p in state2["payments"]), "Pago no persistió"


def simulate_ops(base_url: str, students: list, num_ops: int, seed: int):
    rng = random.Random(seed)
    latencies_ms = []
    existing_order_ids = []
    lock = threading.Lock()

    for idx in range(num_ops):
        student = rng.choice(students)
        action_roll = rng.random()
        t0 = time.perf_counter()

        if action_roll < 0.75:
            order = request_json(
                base_url,
                "POST",
                "/api/orders",
                {"studentId": student["id"], "cart": random_cart(rng)},
            )
            with lock:
                existing_order_ids.append(order["id"])
        elif action_roll < 0.92:
            request_json(
                base_url,
                "POST",
                "/api/payments",
                {
                    "familyKey": family_key(student),
                    "amount": round(rng.uniform(30, 300), 2),
                    "method": "transfer" if rng.random() < 0.7 else "efectivo",
                    "note": "sim",
                },
            )
        else:
            with lock:
                if existing_order_ids:
                    order_id = existing_order_ids.pop(rng.randrange(len(existing_order_ids)))
                else:
                    order_id = None
            if order_id is not None:
                request_json(base_url, "DELETE", f"/api/orders/{order_id}")

        dt_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(dt_ms)

    return latencies_ms


def run_concurrent_orders(base_url: str, students: list, total_orders: int = 600):
    worker_count = 2
    each = total_orders // worker_count
    errors = []
    lock = threading.Lock()

    def worker(seed_offset: int):
        rng = random.Random(1000 + seed_offset)
        for _ in range(each):
            student = rng.choice(students)
            try:
                request_json(
                    base_url,
                    "POST",
                    "/api/orders",
                    {"studentId": student["id"], "cart": random_cart(rng)},
                )
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

    with ThreadPoolExecutor(max_workers=worker_count) as ex:
        futures = [ex.submit(worker, i) for i in range(worker_count)]
        for f in futures:
            f.result()

    if errors:
        raise RuntimeError(f"Errores en concurrencia: {errors[:3]}")


def percentile(values, pct: float):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def main():
    parser = argparse.ArgumentParser(description="Prueba de robustez para cafetería KISS")
    parser.add_argument("--port", type=int, default=8095)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    server_py = project_root / "server.py"

    with tempfile.TemporaryDirectory(prefix="cafe_robust_") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "cafeteria_test.db"
        backup_dir = tmp_path / "backups"
        base_url = f"http://127.0.0.1:{args.port}"

        cmd = [
            sys.executable,
            str(server_py),
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--db-path",
            str(db_path),
            "--backup-dir",
            str(backup_dir),
            "--no-hourly-backup",
        ]
        server_proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            wait_for_health(base_url)

            run_vertical_flow(base_url)

            state = request_json(base_url, "GET", "/api/state")
            students = state["students"]
            assert len(students) >= 10, "No se cargaron alumnos iniciales"

            week_lat = simulate_ops(base_url, students, num_ops=300, seed=42)
            month_lat = simulate_ops(base_url, students, num_ops=1200, seed=777)
            run_concurrent_orders(base_url, students, total_orders=600)

            final_state = request_json(base_url, "GET", "/api/state", timeout=60)
            validate_state(final_state)

        finally:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait(timeout=5)

        # Backup manual check (on-demand backup path)
        backup_cmd = [
            sys.executable,
            str(server_py),
            "--backup-now",
            "--db-path",
            str(db_path),
            "--backup-dir",
            str(backup_dir),
        ]
        backup_res = subprocess.run(backup_cmd, cwd=str(project_root), capture_output=True, text=True, check=True)
        backup_files = sorted(backup_dir.glob("cafeteria_manual_*.db"))
        assert backup_files, "No se creó backup manual"

        # Restore drill: levantar servidor desde backup y verificar que los conteos coinciden.
        restore_port = args.port + 1
        restore_cmd = [
            sys.executable,
            str(server_py),
            "--host",
            "127.0.0.1",
            "--port",
            str(restore_port),
            "--db-path",
            str(backup_files[-1]),
            "--backup-dir",
            str(backup_dir),
            "--no-hourly-backup",
        ]
        restore_proc = subprocess.Popen(
            restore_cmd,
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            restore_url = f"http://127.0.0.1:{restore_port}"
            wait_for_health(restore_url)
            restored_state = request_json(restore_url, "GET", "/api/state", timeout=60)
            assert len(restored_state["students"]) == len(final_state["students"]), "Restore students mismatch"
            assert len(restored_state["orders"]) == len(final_state["orders"]), "Restore orders mismatch"
            assert len(restored_state["payments"]) == len(final_state["payments"]), "Restore payments mismatch"
        finally:
            restore_proc.terminate()
            try:
                restore_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                restore_proc.kill()
                restore_proc.wait(timeout=5)

        all_lat = week_lat + month_lat
        print("=== Robustness Summary ===")
        print(f"Operations week simulation: {len(week_lat)}")
        print(f"Operations month simulation: {len(month_lat)}")
        print(f"Total operations measured: {len(all_lat)}")
        print(f"Latency avg (ms): {statistics.mean(all_lat):.2f}")
        print(f"Latency p95 (ms): {percentile(all_lat, 95):.2f}")
        print(f"Latency max (ms): {max(all_lat):.2f}")
        print(f"Final students: {len(final_state['students'])}")
        print(f"Final orders: {len(final_state['orders'])}")
        print(f"Final payments: {len(final_state['payments'])}")
        print(f"Backup manual created: {backup_files[-1]}")
        print(f"Backup command output: {backup_res.stdout.strip()}")
        print("Backup restore drill: PASS")
        print("RESULT: PASS")


if __name__ == "__main__":
    main()
