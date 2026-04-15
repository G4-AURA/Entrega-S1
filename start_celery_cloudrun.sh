#!/bin/sh
set -e

python -m http.server ${PORT:-8080} &
celery -A config worker --loglevel=info \
  --broker="$CELERY_BROKER_URL?ssl_cert_reqs=CERT_NONE"
