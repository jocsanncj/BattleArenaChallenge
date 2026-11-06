FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000 \
    FIREBASE_ADMIN_CREDENTIALS=/run/secrets/firebase-admin.json

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend /app/backend
COPY server /app/server
COPY shared /app/shared

EXPOSE 8000
VOLUME ["/data"]

CMD ["python", "-m", "server"]
