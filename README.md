# Cafetería Escolar (Producción KISS)

Se mantuvo el diseño del frontend prototipo y se agregó persistencia real con SQLite.

## Qué hace esta versión

- Guarda alumnos, pedidos y pagos en `data/cafeteria.db`.
- Soporta uso concurrente bajo (2 usuarios) con `ThreadingHTTPServer` + transacciones SQLite.
- Activa integridad de datos (`foreign_keys`, `CHECK` constraints).
- Usa `WAL` y `synchronous=FULL` para robustez.
- Hace backup automático por hora en `backups/` (retiene 168 archivos).

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
- Simulación de semana (300 operaciones).
- Simulación de mes (1200 operaciones).
- Concurrencia de 2 usuarios.
- Backup manual y restore drill desde backup.
