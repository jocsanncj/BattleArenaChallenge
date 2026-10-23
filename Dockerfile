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
COPY servidor.py /app/servidor.py
COPY backend /app/backend
COPY datos.py logica.py us10.py us15.py us16.py /app/

EXPOSE 8000
VOLUME ["/data"]

CMD ["python", "/app/servidor.py"]
