#!/usr/bin/env bash
# Build script used by Render (see render.yaml). Runs on every deploy.
set -o errexit

pip install -r requirements.txt

cd event_management_system
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createcachetable

# Optional: create the admin account from DJANGO_SUPERUSER_* variables (never overwrites).
python manage.py ensure_superuser

# Optional: add demo events (safe to repeat).
if [ "${DJANGO_SEED_DEMO:-False}" = "True" ]; then
    python manage.py seed_demo
fi
