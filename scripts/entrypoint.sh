#!/bin/sh
set -e

export CUDA_VISIBLE_DEVICES=""

echo "Waiting for PostgreSQL..."
until uv run python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
print('PostgreSQL is ready')
"; do
  sleep 2
done

uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput

exec uv run gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 300
