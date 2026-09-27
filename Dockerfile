# ---- Stage 1: build the React frontend
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python API + static files
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KACHING_DB=/data/kaching.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 1000 kaching \
    && mkdir -p /data && chown kaching /data

COPY kaching/ kaching/
COPY --from=frontend /frontend/dist frontend/dist
USER kaching
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["python", "-m", "kaching"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
