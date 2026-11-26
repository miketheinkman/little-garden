FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=garden.settings
WORKDIR /app
COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt
COPY manage.py LICENSE ./
COPY LICENSES/ LICENSES/
COPY garden/ garden/
COPY pilot/ pilot/
COPY templates/ templates/
COPY content/ content/
COPY static/ static/
RUN python manage.py collectstatic --settings=garden.common --noinput --verbosity 0 \
    && python manage.py lesson_audio_catalog --settings=garden.common --check \
    && groupadd --gid 10001 garden && useradd --uid 10001 --gid garden --no-create-home garden
USER garden
CMD ["sh", "-ec", "python manage.py migrate --check && exec gunicorn garden.wsgi:application --bind 0.0.0.0:8000 --workers 3 --worker-tmp-dir /tmp"]
