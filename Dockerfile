FROM python:3.11-slim

WORKDIR /app

COPY . /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${PORT:-8080} --db-path /data/cafeteria.db --backup-dir /data/backups --basic-user ${BASIC_AUTH_USER:-} --basic-pass ${BASIC_AUTH_PASS:-}"]
