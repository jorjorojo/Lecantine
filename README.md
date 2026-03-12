# Cafetería Escolar (Producción KISS)

Se mantuvo el diseño del frontend prototipo y se agregó persistencia real con SQLite.

## Qué hace esta versión

- Guarda alumnos, pedidos y pagos en `data/cafeteria.db`.
- Soporta uso concurrente bajo (2 usuarios) con `ThreadingHTTPServer` + transacciones SQLite.
- Activa integridad de datos (`foreign_keys`, `CHECK` constraints).
- Usa `WAL` y `synchronous=FULL` para robustez.
- Hace backup automático por hora en `backups/` (retiene 168 archivos).
- Hace backup automático diario en `backups/` (retiene 90 días).
- Permite editar/eliminar alumnos, pedidos y pagos.
- Incluye buscador de alumnos (alta y selección de alumno).
- Incluye buscador rápido en Estado de Cuenta y export CSV del periodo.
- Incluye pestaña **CSV Diario** para generar/listar/descargar CSV por fecha.
- Si se borra todo en producción, no vuelve a sembrar alumnos dummy al reiniciar.

## Producción real (Internet público)

Objetivo correcto: que entren desde cualquier lugar, con datos móviles o WiFi, usando una URL HTTPS pública.

## URL pública (Querétaro + Monterrey) - camino KISS recomendado

1. Sube este proyecto a GitHub.
2. Crea un proyecto en Railway y despliega desde ese repo.
3. Agrega un Volume y móntalo en `/data`.
4. Configura el start command:

   ```bash
   python3 server.py --host 0.0.0.0 --port $PORT --db-path /data/cafeteria.db --backup-dir /data/backups --basic-user $BASIC_AUTH_USER --basic-pass $BASIC_AUTH_PASS
   ```

5. En Networking, haz click en **Generate Domain** para obtener la URL pública HTTPS.
6. Configura variables de entorno `BASIC_AUTH_USER` y `BASIC_AUTH_PASS` para que solo ellos 2 entren.
7. Comparte esa URL con los dos usuarios. Ellos pueden entrar con cualquier red (3G/4G/5G o WiFi).

Notas:

- Con SQLite + Volume se usa 1 sola instancia (ideal para 2 usuarios y baja carga).
- Con volume, un redeploy puede tener unos segundos de downtime.
- Zona horaria recomendada: `APP_TIMEZONE=America/Monterrey`.

## Robustez validada

Prueba automatizada ejecutada (`RESULT: PASS`) con:

- Flujo vertical completo: alta alumno -> pedido -> pago -> eliminar pedido.
- Editar pago + eliminar pago.
- Simulación de semana (300 operaciones).
- Simulación de mes (1200 operaciones).
- Concurrencia de 2 usuarios.
- Backup manual y restore drill desde backup.

## Export CSV

Endpoint:

```bash
GET /api/export.csv?start=YYYY-MM-DD&end=YYYY-MM-DD&paymentType=transfer|cole&kind=accounts|orders
```

Notas:

- `start` y `end` son obligatorias en uso normal desde UI (la UI ya las manda).
- `paymentType` es opcional (`transfer` o `cole`).
- `kind` define el CSV:
  - `orders`: detalle de pedidos (quién pidió, qué pidió, cuánto y cuándo).
  - `accounts`: estado de cuentas + pagos por familia/alumno.
- Compatibilidad: `summary`, `movements` y `balances` se aceptan como alias legados.
- Devuelve CSV descargable (UTF-8 con BOM para Excel).

## CSV diario (en la app)

- La app guarda snapshots CSV diarios en `daily_csv/`.
- Se generan automáticamente 2 archivos diarios (`orders`, `accounts`) al iniciar y después de cada cambio (pedido/pago/alumno).
- Además, un scheduler los asegura en segundo plano cada pocos minutos.
- Desde la pestaña **CSV Diario** puedes:
  - Cambiar tipo de CSV (Pedidos, Cuentas/Pagos).
  - Generar CSV de cualquier fecha para ese tipo.
  - Ver historial de archivos.
  - Descargar cada archivo.

Endpoints:

```bash
GET /api/daily-csv?limit=120&kind=accounts|orders
POST /api/daily-csv/generate   # body opcional: {"date":"YYYY-MM-DD","kind":"accounts|orders"}
GET /api/daily-csv/download?date=YYYY-MM-DD&kind=accounts|orders
```

## Operación (Fase 7)

Checklist mínima semanal:

1. Verificar salud:

   ```bash
   curl -s -u "$BASIC_AUTH_USER:$BASIC_AUTH_PASS" https://TU-DOMINIO/api/health
   ```

2. Smoke test en vivo (1 comando):

   ```bash
   python3 tests/ops_smoke.py --base-url https://TU-DOMINIO --user "$BASIC_AUTH_USER" --password "$BASIC_AUTH_PASS"
   ```

3. Backup manual (desde shell del servidor/Railway):

   ```bash
   python3 server.py --backup-now --db-path /data/cafeteria.db --backup-dir /data/backups
   ```

4. Drill de restore (local):

   ```bash
   python3 tests/robustness_simulation.py --port 8095
   ```

## Arranque en Cero (producción real)

Si quieres limpiar todo para empezar desde cero:

```bash
python3 tests/reset_live_data.py --base-url https://TU-DOMINIO --user "$BASIC_AUTH_USER" --password "$BASIC_AUTH_PASS"
```

Qué hace:

1. Guarda snapshot local previo.
2. Elimina pagos, pedidos y alumnos.
3. Verifica conteos finales en cero.
