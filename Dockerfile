FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    APP_ENV=production DATA_DIR=/data DB_PATH=/data/agency.db PORT=10000
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 agency \
    && useradd --uid 10001 --gid agency --no-create-home agency \
    && mkdir -p /data && chown agency:agency /data
COPY backend/app /app/backend/app
COPY backend/prompts /app/backend/prompts
COPY backend/certs /app/backend/certs
COPY deploy/start_backend.py /app/start_backend.py
WORKDIR /app/backend
EXPOSE 10000
# The entrypoint fixes mount ownership, then drops privileges before uvicorn.
CMD ["python", "/app/start_backend.py"]
