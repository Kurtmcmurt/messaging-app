#!/bin/sh
set -e
until pg_isready -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
  sleep 1
done
python manage.py migrate --noinput
python manage.py loaddata users recipients threads messages 2>/dev/null || true
exec "$@"
