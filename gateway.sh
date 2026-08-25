#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# Weaver Write — Gateway (unified entry point / service runner)
# ═══════════════════════════════════════════════════════════
# Starts the web UI and keeps it running; use as the always-on service.
cd "$(dirname "$0")"

PORT="${WEAVER_PORT:-8848}"

case "${1:-start}" in
    start)
        echo "Starting Weaver Write gateway on port $PORT..."
        python3 weaver.py serve --port "$PORT"
        ;;
    stop)
        echo "Stopping gateway..."
        pkill -f "weaver.py serve" 2>/dev/null && echo "Stopped." || echo "Not running."
        ;;
    restart)
        "$0" stop; sleep 1; "$0" start
        ;;
    status)
        if pgrep -f "weaver.py serve" >/dev/null; then
            echo "Gateway is running at http://127.0.0.1:$PORT"
        else
            echo "Gateway is not running."
        fi
        ;;
    *)
        echo "Usage: gateway.sh {start|stop|restart|status}"
        ;;
esac
