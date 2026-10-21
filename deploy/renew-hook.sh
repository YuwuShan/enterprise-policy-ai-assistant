#!/bin/sh
set -eu

# Certbot invokes this only after successful renewal. Ignore unrelated certificates.
if [ "${RENEWED_LINEAGE:-}" != "/etc/letsencrypt/live/oa-demo" ]; then
    exit 0
fi
cd /opt/oa-assistant
/usr/bin/docker compose -f compose.yaml -f compose.cloud.yaml exec -T nginx nginx -t
/usr/bin/docker compose -f compose.yaml -f compose.cloud.yaml exec -T nginx nginx -s reload
