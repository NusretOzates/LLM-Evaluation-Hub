#!/bin/sh
set -eu

upstream="${API_UPSTREAM:-http://api:8000}"
attempt=0
until wget -q -O /dev/null "${upstream}/datasets"; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "catalog API at ${upstream} did not become ready" >&2
    exit 1
  fi
  sleep 1
done

exec /docker-entrypoint.sh "$@"
