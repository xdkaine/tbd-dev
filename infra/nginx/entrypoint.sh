#!/bin/sh
# Nginx entrypoint with config reload watcher.
#
# Starts nginx, then polls a flag file written by the API container.
# When the flag file changes, validates and reloads nginx config.
set -e

RELOAD_FLAG="/var/run/nginx-reload/reload"

# Start nginx in background
nginx -g "daemon off;" &
NGINX_PID=$!

echo "[nginx-reload] Watching $RELOAD_FLAG for reload signals..."

LAST_CONTENT=""

while kill -0 "$NGINX_PID" 2>/dev/null; do
    if [ -f "$RELOAD_FLAG" ]; then
        CURRENT=$(cat "$RELOAD_FLAG" 2>/dev/null || echo "")
        if [ "$CURRENT" != "$LAST_CONTENT" ] && [ -n "$CURRENT" ]; then
            LAST_CONTENT="$CURRENT"
            echo "[nginx-reload] Reload signal detected ($CURRENT), validating config..."
            if nginx -t 2>&1; then
                nginx -s reload
                echo "[nginx-reload] Nginx reloaded successfully"
            else
                echo "[nginx-reload] ERROR: Config validation failed, skipping reload"
            fi
        fi
    fi
    sleep 2
done

# If nginx exits, exit the script too
wait "$NGINX_PID"
