# PitWall in one image: the API + the built frontend, served by uvicorn on port 8000.
#   docker build -t pitwall .
#   docker run -p 8000:8000 -v "$PWD/data:/data" pitwall
# Data (SQLite DB, lap files, trained models) lives in the /data volume.

# ---- frontend build ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
# LightGBM needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/f1p backend/f1p
RUN pip install --no-cache-dir ./backend

COPY --from=web /web/dist /app/frontend/dist

ENV F1P_DATA_DIR=/data \
    F1P_STATIC_DIR=/app/frontend/dist \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 f1 && mkdir -p /data && chown f1 /data
USER f1
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "f1p.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
