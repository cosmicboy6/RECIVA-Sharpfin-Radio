#!/bin/sh
set -u
export DISPLAY=:99

DNS_SERVER="${UPSTREAM_DNS:-192.168.0.1}"
KEY="${DES_KEY:-}"

case "$KEY" in
  ''|'<DES_KEY>')
    echo "configure_gui: DES_KEY fehlt oder ist noch Platzhalter" >&2
    exit 1
    ;;
esac

W=""
i=0
while [ "$i" -lt 60 ]; do
  W="$(xdotool search --name 'Reciva Server' 2>/dev/null | head -1)"
  [ -n "$W" ] && break
  i=$((i + 1))
  sleep 0.5
done
[ -z "$W" ] && { echo "configure_gui: no window"; exit 1; }

xdotool windowactivate "$W" 2>/dev/null || true
sleep 0.5

click() {
  xdotool mousemove --window "$W" "$1" "$2" click 1
  sleep 0.2
}

# DNS server field (Upstream/Router)
click 300 38
xdotool key --window "$W" ctrl+a
xdotool type --window "$W" --delay 15 "$DNS_SERVER"
sleep 0.3

# Provide patch checkbox (center 18,157)
scrot -u -o /tmp/cfg.png 2>/dev/null
if ! python3 - <<'PY'
from PIL import Image
im = Image.open('/tmp/cfg.png').convert('L')
vals = [im.getpixel((18 + dx, 157 + dy)) for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
raise SystemExit(0 if sum(vals) / len(vals) < 120 else 1)
PY
then
  click 18 157
fi
sleep 2

# Patch file radio
click 50 184
sleep 0.3

# Patch file combo: focus, open, choose first entry, commit
click 400 187
xdotool key --window "$W" alt+Down
sleep 0.4
xdotool key --window "$W" Home
xdotool key --window "$W" Return
sleep 0.6

# Full server mode checkbox (center 18,344)
scrot -u -o /tmp/cfg.png 2>/dev/null
if ! python3 - <<'PY'
from PIL import Image
im = Image.open('/tmp/cfg.png').convert('L')
vals = [im.getpixel((18 + dx, 344 + dy)) for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
raise SystemExit(0 if sum(vals) / len(vals) < 120 else 1)
PY
then
  click 18 344
fi
sleep 0.3

# Radio DES key (8 bytes, device-specific; serial is <SERIAL>)
click 200 292
xdotool key --window "$W" ctrl+a
xdotool type --window "$W" --delay 15 "$KEY"
sleep 0.3

# Start session
click 286 455
sleep 1
echo "configure_gui: done"
