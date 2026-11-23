#!/bin/sh
set -e

# Der DES-Key kommt zur Laufzeit aus .env und wird nie ins Image gebacken.
if [ -z "${DES_KEY:-}" ] || [ "${DES_KEY:-}" = "<DES_KEY>" ]; then
  echo "entrypoint: DES_KEY fehlt oder ist noch Platzhalter" >&2
  exit 1
fi

rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
sleep 1

export DISPLAY=:99
fluxbox >/tmp/fluxbox.log 2>&1 &
sleep 1

dbus-daemon --session --fork --print-address=1 > /tmp/dbus_addr
export DBUS_SESSION_BUS_ADDRESS="$(cat /tmp/dbus_addr)"
export GTK_MODULES=gail:atk-bridge
export NO_AT_BRIDGE=0

cd /opt/RecivaServer

python3 -m http.server 8080 --bind 0.0.0.0 -d /opt/RecivaServer/www8080 >/tmp/http8080.log 2>&1 &
python3 /opt/ntp_server.py >/tmp/ntp_server.log 2>&1 &
/opt/configure_gui.sh >/tmp/configure_gui.log 2>&1 &
python3 /opt/sync_sharpfin_menu.py >/tmp/sync_sharpfin.log 2>&1 &

exec ./server
