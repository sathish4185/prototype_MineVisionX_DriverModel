#!/bin/bash
export DISPLAY=:0
export XAUTHORITY=$(ls -t /tmp/serverauth.* 2>/dev/null | head -n 1)
pkill -9 -f chromium 2>/dev/null || true
pkill -9 -f keyring 2>/dev/null || true
sleep 1
exec /usr/lib/chromium/chromium \
  --password-store=basic \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --kiosk \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  http://127.0.0.1:5000
