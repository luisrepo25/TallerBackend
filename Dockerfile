FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    libproj-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    postgresql-client \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements-dev.txt

COPY . .

# Produccion (Cloud Run): gunicorn escucha en $PORT, con hilos para que una subida lenta
# de foto no deje al servidor sin atender. En desarrollo docker-compose.yml sobreescribe
# este comando con runserver.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120"]
