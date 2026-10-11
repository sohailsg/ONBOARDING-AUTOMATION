#!/bin/sh
# API entrypoint. START_WORKER=1 also runs the arq worker in this container
# (single free-tier Render service). Listens on $PORT (Render) or $API_PORT.
if [ "${START_WORKER:-0}" = "1" ]; then
  arq worker.jobs.WorkerSettings &
fi
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-${API_PORT:-8000}}"
