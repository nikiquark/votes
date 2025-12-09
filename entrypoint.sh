#!/bin/sh
set -e

python manage.py collectstatic --noinput || echo "collectstatic failed (maybe no static configured)"

gunicorn votes.wsgi:application --bind 0.0.0.0:8000