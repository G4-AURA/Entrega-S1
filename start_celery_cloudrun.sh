#!/bin/sh
set -e

python -m http.server ${PORT:-8080} &
export CELERY_BROKER_USE_SSL='{"ssl_cert_reqs": 0}'
export CELERY_REDIS_BACKEND_USE_SSL='{"ssl_cert_reqs": 0}'
celery -A config worker --loglevel=info
