#!/usr/bin/env bash
# Install/repair all Python libraries the tools need
set -e
cd "$(dirname "$0")"
echo "Installing all Weaver Write libraries..."
if [ -n "$TERMUX_VERSION" ]; then
    pip install -r requirements.txt
else
    python3 -m pip install -r requirements.txt --break-system-packages 2>/dev/null || \
        python3 -m pip install -r requirements.txt
fi
echo "Done. Verify with:  weaver doctor"
