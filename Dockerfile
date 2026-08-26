FROM python:3.12-slim

WORKDIR /app

# deps first so Docker caches the layer
COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir -r requirements-ai.txt

COPY src/ ./src/
COPY web/ ./web/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    LAWHUB_PUBLIC=1

# regenerate the frontend data from the Python corpus at build time
RUN python scripts/export_web.py

# Cloud Run / Render inject $PORT
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn lawhub.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
