#!/usr/bin/env bash
# Komfort-Installer fuer das RECIVA-Sharpfin-Radio Deployment-Paket.
# Er aendert NICHTS am Radio und beruehrt keine bestehenden Container,
# ausser denen mit den hier festgelegten Namen.
set -euo pipefail

ORIG_PWD="$(pwd)"
cd "$(dirname "$0")/.."

SERVER_DIR=""
PATCH_FILE=""
MODEL="ipdio"

usage() {
  cat <<'EOF'
Usage: ./scripts/install.sh [Optionen]

Optionen:
  -s, --server-dir PATH   Quellordner mit dem Patchserver-Paket
                          (muss ./server enthalten).
  -p, --patch-file PATH   Patch-Datei (Standard: je nach Modell).
  -m, --model MODEL       ipdio (Standard) oder ipduo/generic.
                          ipdio  -> sharpfin-base_0.3_IPdio.patch
                          ipduo  -> sharpfin-base_0.3_generic.patch
                                    (= offizieller Sharpfin Base 0.3)
  -h, --help              Hilfe anzeigen.

Fehlen -s/-p, werden die mitgelieferten RecivaServer/- und files/-Dateien
verwendet (siehe THIRD_PARTY.md).
EOF
}

die() { echo "FEHLER: $*" >&2; exit 1; }

md5_of() {
  if command -v md5sum >/dev/null 2>&1; then
    md5sum "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl md5 -r "$1" | awk '{print $1}'
  else
    die "weder md5sum noch openssl gefunden"
  fi
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    die "docker compose oder docker-compose nicht gefunden"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--server-dir)
      [[ $# -ge 2 ]] || die "$1 braucht einen Pfad"
      SERVER_DIR="$2"
      shift 2
      ;;
    -p|--patch-file)
      [[ $# -ge 2 ]] || die "$1 braucht einen Pfad"
      PATCH_FILE="$2"
      shift 2
      ;;
    -m|--model)
      [[ $# -ge 2 ]] || die "$1 braucht ein Modell"
      MODEL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unbekannte Option: $1"
      ;;
  esac
done

resolve_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *)  printf '%s/%s\n' "$ORIG_PWD" "$1" ;;
  esac
}

if [[ -n "$SERVER_DIR" ]]; then
  SERVER_DIR="$(resolve_path "$SERVER_DIR")"
fi
if [[ -n "$PATCH_FILE" ]]; then
  PATCH_FILE="$(resolve_path "$PATCH_FILE")"
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Hinweis: .env wurde aus .env.example angelegt - bitte ausfuellen und erneut starten."
fi

# .env enthaelt nur lokale Werte und ist gitignored.
set -a
# shellcheck disable=SC1091
source ./.env
set +a

required=(RECIVA_NET SUBNET GATEWAY PARENT_IFACE PATCHSERVER_IP DNS_PROXY_IP UPSTREAM_DNS RADIO_IP DES_KEY SERIAL)
for key in "${required[@]}"; do
  value="${!key-}"
  if [[ -z "$value" || "$value" == \<*\> ]]; then
    die "$key in .env ausfuellen (Platzhalter sind nicht erlaubt)"
  fi
done

if [[ -n "$SERVER_DIR" ]]; then
  [[ -d "$SERVER_DIR" ]] || die "Server-Ordner fehlt: $SERVER_DIR"
  rm -rf RecivaServer
  mkdir -p RecivaServer
  cp -a "$SERVER_DIR"/. RecivaServer/
elif [[ ! -d RecivaServer ]]; then
  die "RecivaServer/ fehlt - mit --server-dir angeben oder manuell kopieren"
fi
[[ -f RecivaServer/server ]] || die "RecivaServer/server fehlt"

case "$MODEL" in
  ipdio)
    default_patch="files/sharpfin-base_0.3_IPdio.patch"
    expected_md5="043934970007ed0e83ad62ecb8d54b02"
    ;;
  ipduo|generic)
    default_patch="files/sharpfin-base_0.3_generic.patch"
    expected_md5="da6ffd368350f575dc5e706ee1727e4e"
    ;;
  *)
    die "unbekanntes Modell: $MODEL (ipdio|ipduo|generic)"
    ;;
esac

mkdir -p files
if [[ -n "$PATCH_FILE" ]]; then
  [[ -f "$PATCH_FILE" ]] || die "Patch-Datei fehlt: $PATCH_FILE"
  cp -f "$PATCH_FILE" files/sharpfin-base_0.3_IPdio.patch
elif [[ ! -f "$default_patch" ]]; then
  die "$default_patch fehlt - mit --patch-file angeben"
else
  cp -f "$default_patch" files/sharpfin-base_0.3_IPdio.patch
fi

patch_md5="$(md5_of files/sharpfin-base_0.3_IPdio.patch)"
if [[ "$patch_md5" != "$expected_md5" ]]; then
  die "falsche Patchdatei fuer $MODEL: MD5 $patch_md5 statt $expected_md5"
fi
echo "Patchdatei fuer $MODEL geprueft (MD5 $patch_md5)"

python3 patch_server.py RecivaServer/server

if ! docker network inspect "$RECIVA_NET" >/dev/null 2>&1; then
  echo "Erstelle macvlan-Netz $RECIVA_NET ..."
  docker network create -d macvlan \
    --subnet "$SUBNET" \
    --gateway "$GATEWAY" \
    -o parent="$PARENT_IFACE" \
    -o macvlan_mode=bridge \
    "$RECIVA_NET"
else
  echo "macvlan-Netz $RECIVA_NET existiert bereits."
fi

COMPOSE="$(compose_cmd)"
echo "Baue und starte Container ..."
# shellcheck disable=SC2086
$COMPOSE up -d --build

echo
echo "Fertig. Jetzt passiv pruefen:"
echo "  ./scripts/verify.sh"
echo
echo "Danach am Radio: DNS dauerhaft auf $DNS_PROXY_IP stellen und per Power-Button neu starten."
