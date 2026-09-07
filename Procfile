web: gunicorn example.wsgi --bind 0.0.0.0:${PORT:-8000} --access-logfile - --log-file -
release: python manage.py migrate --noinput
