#!/usr/bin/env bash
# Passive Pruefung des deployten Stacks - ohne Radio-Interaktion.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "FEHLER: .env fehlt (cp .env.example .env)"; exit 1; }
set -a
# shellcheck disable=SC1091
source ./.env
set +a

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "FEHLER: docker compose nicht gefunden"
  exit 1
fi

fail=0
ok()   { echo "  OK    $*"; }
bad()  { echo "  FAIL  $*"; fail=1; }
warn() { echo "  WARN  $*"; }

echo "== Container =="
# shellcheck disable=SC2086
$COMPOSE ps

echo
echo "== Patchserver-Binary =="
expected="2d899b010d4f5544a62183fe401a34e7970b189a4ddaaf99d6808b63f31689d0"
actual="$(docker exec reciva-patchserver sha256sum /opt/RecivaServer/server 2>/dev/null | awk '{print $1}' || true)"
if [[ "$actual" == "$expected" ]]; then
  ok "SHA256 ${actual:0:12}... entspricht dem 30er-Clamp-Build"
else
  bad "SHA256 unerwartet: ${actual:-<keine Ausgabe>}"
fi

echo
echo "== DNS-Proxy =="
dns_result="$(docker exec reciva-patchserver python3 - "$DNS_PROXY_IP" "$PATCHSERVER_IP" <<'PY' 2>&1 || true
import socket
import struct
import sys

proxy, expected = sys.argv[1], sys.argv[2]


def query(name):
    packet = struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    for label in name.split("."):
        packet += bytes([len(label)]) + label.encode("ascii")
    packet += b"\x00" + struct.pack("!HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    s.sendto(packet, (proxy, 53))
    data, _ = s.recvfrom(2048)
    s.close()
    return data


try:
    reciva = query("www.reciva.com")
    other = query("example.com")
    hit = socket.inet_aton(expected) in reciva
    rcode = reciva[3] & 0x0F
    other_rcode = other[3] & 0x0F
    print("reciva=%s rcode=%d external_rcode=%d"
          % ("OK" if hit else "FAIL", rcode, other_rcode))
    raise SystemExit(0 if hit and rcode == 0 and other_rcode == 0 else 1)
except Exception as exc:
    print("DNS-Fehler: %r" % exc)
    raise SystemExit(1)
PY
)"
if echo "$dns_result" | grep -q '^reciva=OK'; then
  ok "www.reciva.com -> $PATCHSERVER_IP, externe Domain -> Upstream"
else
  bad "DNS-Check: $dns_result"
fi

echo
echo "== Pagination =="
for view in 112_0_0 0_40_0; do
  counts="$(docker exec reciva-patchserver python3 - "$view" <<'PY' 2>&1 || true
import re
import sys
import urllib.request

view = sys.argv[1]
result = []
for start in (0, 30, 60, 90):
    url = ("http://127.0.0.1/portal-newformat/stations.xml"
           "?request_view=%s&view_type=stations_only&start=%d&count=30"
           % (view, start))
    body = urllib.request.urlopen(url, timeout=10).read().decode("utf-8", "replace")
    result.append(str(len(re.findall(r"<stream\s+id=", body))))
print(" ".join(result))
PY
)"
  if [[ "$counts" == "30 30 30 10" ]]; then
    ok "view $view: $counts"
  else
    bad "view $view: ${counts:-<keine Ausgabe>} (erwartet 30 30 30 10)"
  fi
done

echo
echo "== Senderdaten (informational) =="
station_info="$(docker exec reciva-patchserver python3 - <<'PY' 2>&1 || true
import os
import re

base = "/opt/RecivaServer/stations"
view_dir = os.path.join(base, "views")
views = len([n for n in os.listdir(view_dir) if n.endswith(".xml")]) if os.path.isdir(view_dir) else -1
try:
    text = open(os.path.join(base, "stations.xml"), encoding="utf-8", errors="replace").read()
except OSError:
    text = ""
match = re.search(r"<count>\s*112,0,(\d+)", text)
print("views=%d de_count=%s" % (views, match.group(1) if match else "MISSING"))
PY
)"
echo "  $station_info"
if [[ "$station_info" == "views=121 de_count=100" ]]; then
  ok "Import-Stand 121 Views / 100 Deutschland-Sender erreicht"
else
  warn "Import-Stand abweichend - Senderdaten-Import pruefen (README Abschnitt 8)"
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "Ergebnis: gruen. Radio-Tests weiterhin nur mit Freigabe am Geraet."
else
  echo "Ergebnis: FEHLER. Logs mit 'docker logs reciva-patchserver' und 'docker logs reciva-dnsproxy' pruefen."
  exit 1
fi
