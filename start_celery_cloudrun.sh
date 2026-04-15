#!/bin/sh
set -e

export CELERY_BROKER_URL="${CELERY_BROKER_URL}?ssl_cert_reqs=CERT_NONE"

python -m http.server ${PORT:-8080} &
celery -A config worker --loglevel=info
