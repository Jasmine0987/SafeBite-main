# Build from the repo root:  docker build -t safebite .
# Run:  docker run -p 8000:8000 -v safebite-data:/data safebite
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr libzbar0 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
# CPU-only torch keeps the image small
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

ENV SERVE_FRONTEND=1 \
    ALLOWED_ORIGIN_REGEX="" \
    SAFEBITE_DB_PATH=/data/safebite.db
VOLUME /data
WORKDIR /srv/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
