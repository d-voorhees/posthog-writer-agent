#!/bin/sh
set -e

# The chroma_store directory lives in the container's ephemeral
# filesystem (no persistent volume attached for this demo-scale
# project). If it's missing or empty, run ingestion once before
# starting the server. On a fresh deploy this costs under a minute
# for this doc set; a larger doc set or a need for ingestion to
# survive machine restarts without re-running would be the signal
# to attach a real Fly volume instead.
if [ ! -d "/app/chroma_store" ] || [ -z "$(ls -A /app/chroma_store 2>/dev/null)" ]; then
  echo "No existing chroma_store found, running ingestion..."
  python ingest.py
fi

exec python server.py --http
