FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        binutils \
        gdal-bin \
        libgdal-dev \
        libproj-dev \
        libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

COPY . .
# collect static (opcional en build, el || true evita que falle si faltan variables)
RUN python manage.py collectstatic --noinput || true
RUN chmod +x /app/docker/entrypoint.prod.sh

# Cloud Run injects the PORT environment variable automatically
EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.prod.sh"]
CMD exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3