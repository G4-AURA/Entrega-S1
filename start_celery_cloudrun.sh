#!/bin/sh
set -e

python -m http.server ${PORT:-8080} &
celery -A config worker --loglevel=info
