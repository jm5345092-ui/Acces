#!/bin/sh
# Local docker-compose keeps the original split (worker only runs the job
# loop; see backend/Dockerfile for the separate `api` container). Railway
# cannot mount one volume into two services, so there APKLAB_COMBINED_API=1
# runs the job loop and the HTTP API together in this one container, backed
# by a single shared volume.
set -e

# A fresh Railway volume mounts empty at /data, shadowing the directories
# created at image build time — recreate them before anything touches the
# sqlite file or storage root.
mkdir -p /data/storage /data/db

if [ "${APKLAB_COMBINED_API:-0}" = "1" ]; then
  python3 -m app.workers.job_worker &
  # Tried "::" for dual-stack (Railway's private network resolves both
  # IPv4 and IPv6) but this host enforces bindv6only, which made "::"
  # IPv6-ONLY and broke Railway's own healthcheck entirely. Back to
  # 0.0.0.0 — the nginx-side "listen [::]:80" fix covers the frontend,
  # which is the leg that was actually seeing the intermittent timeouts.
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
else
  exec python3 -m app.workers.job_worker
fi
