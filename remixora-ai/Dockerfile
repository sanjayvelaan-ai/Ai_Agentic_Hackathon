FROM node:22-slim AS node_runtime
FROM python:3.12-slim
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-transcription.txt ./
ARG WITH_WHISPER=0
RUN pip install --no-cache-dir -r requirements.txt && if [ "$WITH_WHISPER" = "1" ]; then pip install --no-cache-dir -r requirements-transcription.txt; fi
COPY app ./app
COPY scripts ./scripts
RUN mkdir -p /data && useradd --uid 10001 --create-home remixora && chown -R remixora:remixora /data /app
USER remixora
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)" || exit 1
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1","--proxy-headers"]
