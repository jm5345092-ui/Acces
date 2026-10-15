# API container: deliberately NO Java / Apktool / Android SDK.
# It only serves REST+SSE and enqueues jobs onto the queue; the worker
# container (see worker/Dockerfile) is the only place Android tooling runs.
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 apklab
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /data/storage /data/db && chown -R apklab:apklab /data /app
USER apklab

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
