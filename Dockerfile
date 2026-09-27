FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KACHING_DB=/data/kaching.db \
    KACHING_CHARTS=/data/charts

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 1000 kaching \
    && mkdir -p /data && chown kaching /data

COPY kaching/ kaching/
USER kaching
VOLUME /data
ENTRYPOINT ["python", "-m", "kaching"]
CMD ["--help"]
