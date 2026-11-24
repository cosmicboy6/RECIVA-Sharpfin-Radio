#!/usr/bin/env bash
# Vollständiger manueller Update-Weg: RadioBrowser -> M3U -> Reciva-Views -> Container.
# Standardmäßig wird nur das Paket gebaut; mit --apply wird es in den Container kopiert.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/tools"
WORK="${RB_WORK:-$TOOLS/work}"
CONTAINER="${RECIVA_CONTAINER:-reciva-patchserver}"
REMOTE_STATIONS="/opt/RecivaServer/stations"
APPLY=0
SKIP_FETCH=0

usage() {
  cat <<'EOF'
Usage: ./tools/update_stations.sh [Optionen]

Optionen:
  -w, --work DIR    Arbeitsverzeichnis (Default: tools/work)
  -c, --container N Patchserver-Container (Default: reciva-patchserver)
      --skip-fetch  rb_countries.json nicht erneut laden
      --apply       Paket in den Container kopieren (sonst nur bauen)
  -h, --help        Hilfe

Nach --apply am Radio einmal den Power-Button drücken, sonst bleibt die
alte stations.xml im Menü-Cache hängen.
EOF
}

die() { echo "FEHLER: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -w|--work)      [[ $# -ge 2 ]] || die "$1 braucht ein Verzeichnis"; WORK="$2"; shift 2 ;;
    -c|--container) [[ $# -ge 2 ]] || die "$1 braucht einen Namen"; CONTAINER="$2"; shift 2 ;;
    --skip-fetch)   SKIP_FETCH=1; shift ;;
    --apply)        APPLY=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *)              die "unbekannte Option: $1" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "python3 fehlt"
command -v docker >/dev/null 2>&1 || die "docker fehlt"

mkdir -p "$WORK"
export RB_WORK="$WORK"

echo "== 1. Aktuellen stations-Baum aus $CONTAINER holen =="
CURRENT="$WORK/stations_current"
rm -rf "$CURRENT/stations"
mkdir -p "$CURRENT"
docker cp "$CONTAINER:$REMOTE_STATIONS" "$CURRENT/stations"
STATIONS_XML="$CURRENT/stations/stations.xml"
[[ -f "$STATIONS_XML" ]] || die "stations.xml fehlt im kopierten Baum"
export STATIONS_XML

echo "== 2. RadioBrowser-Länderliste laden =="
if [[ "$SKIP_FETCH" -eq 0 || ! -f "$WORK/rb_countries.json" ]]; then
  command -v curl >/dev/null 2>&1 || die "curl fehlt (oder --skip-fetch mit vorhandener rb_countries.json)"
  curl -fsSL "https://de1.api.radio-browser.info/json/countries" \
    -o "$WORK/rb_countries.json"
fi

echo "== 3. Länder: 100 Sender pro Land abrufen und Views bauen =="
python3 "$TOOLS/build_radiobrowser_100.py"
python3 "$TOOLS/build_reciva_views_100.py"
COUNTRY_STATIONS="$WORK/reciva_stations_pkg_100/stations"

echo "== 4. Genres: 100 Sender pro Genre abrufen und Views bauen =="
python3 "$TOOLS/build_radiobrowser_genres.py"
STATIONS_XML="$COUNTRY_STATIONS/stations.xml" python3 "$TOOLS/build_reciva_genres.py"
GENRE_STATIONS="$WORK/reciva_genres_pkg/stations"

echo "== 5. Finalen Baum zusammenstellen (bestehende Views bleiben erhalten) =="
FINAL="$WORK/stations_new"
rm -rf "$FINAL"
mkdir -p "$FINAL"
cp -a "$CURRENT/stations/." "$FINAL/"
mkdir -p "$FINAL/views"
cp -a "$COUNTRY_STATIONS/views/." "$FINAL/views/"
cp -a "$GENRE_STATIONS/views/." "$FINAL/views/"
cp -f "$GENRE_STATIONS/stations.xml" "$FINAL/stations.xml"

COUNTRY_VIEWS="$(find "$FINAL/views" -maxdepth 1 -type f -name 'view_*_0_0.xml' | wc -l)"
GENRE_VIEWS="$(find "$FINAL/views" -maxdepth 1 -type f -name 'view_0_*_0.xml' | wc -l)"
ALL_VIEWS="$(find "$FINAL/views" -maxdepth 1 -type f -name 'view_*.xml' | wc -l)"
echo "Länder-Views: $COUNTRY_VIEWS / Genre-Views: $GENRE_VIEWS / gesamt: $ALL_VIEWS"
[[ "$COUNTRY_VIEWS" -ge 48 && "$GENRE_VIEWS" -ge 64 ]] \
  || die "unerwartete View-Anzahl – Paket nicht übernehmen"

tar czf "$WORK/reciva_update.tar.gz" -C "$FINAL" .
echo "Paket: $WORK/reciva_update.tar.gz"

if [[ "$APPLY" -eq 0 ]]; then
  echo "Nur gebaut. Zum Deployen erneut mit --apply aufrufen."
  exit 0
fi

echo "== 6. Backup + Deploy =="
docker cp "$WORK/reciva_update.tar.gz" "$CONTAINER:/tmp/reciva_update.tar.gz"
docker exec "$CONTAINER" sh -c \
  'cd /opt/RecivaServer && tar czf stations.bak-$(date +%Y%m%d-%H%M%S).tar.gz stations && tar xzf /tmp/reciva_update.tar.gz -C stations'
echo "Deployed. Jetzt am Radio den Power-Button drücken (Menü-Cache!)."
