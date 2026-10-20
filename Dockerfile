FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000 \
    LEGACY_USERS_FILE=/legacy/DatosUser.json \
    PUBLIC_BASE_URL=http://localhost:8000

WORKDIR /app
COPY servidor.py /app/servidor.py
COPY backend /app/backend

EXPOSE 8000
VOLUME ["/data"]

CMD ["python", "/app/servidor.py"]
