FROM node:20-alpine AS frontend
WORKDIR /build
COPY package.json vite.config.js ./
COPY frontend ./frontend
RUN npm install && npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY static ./static
COPY --from=frontend /build/static/react ./static/react
COPY translations.py app.py ./

RUN mkdir -p /app/static/uploads /app/backups
RUN mkdir -p /data \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 45000 8765

CMD ["python", "app.py"]
