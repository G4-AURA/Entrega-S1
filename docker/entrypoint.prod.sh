#!/bin/sh
set -e

echo "[entrypoint] Waiting for database..."
python - <<'PY'
import os
import time
import psycopg

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "5432"))
name = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

if not all([name, user, password]):
    raise SystemExit("Missing DB_NAME, DB_USER or DB_PASSWORD environment variables.")

for attempt in range(1, 31):
    try:
        psycopg.connect(host=host, port=port, dbname=name, user=user, password=password).close()
        print("[entrypoint] Database is ready.")
        break
    except Exception as exc:
        print(f"[entrypoint] Database unavailable ({attempt}/30): {exc}")
        time.sleep(2)
else:
    raise SystemExit("Database did not become available in time.")
PY

echo "[entrypoint] Applying migrations..."
python manage.py migrate --noinput


echo "[entrypoint] Ensuring default superuser exists..."
python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin")
email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "admin123")

user, created = User.objects.get_or_create(
    username=username,
    defaults={"email": email, "is_staff": True, "is_superuser": True},
)

if created:
    user.set_password(password)
    user.save()
    print(f"Default superuser '{username}' created.")
else:
    print(f"Default superuser '{username}' already exists.")
PY

echo "[entrypoint] Starting application..."
exec "$@"
