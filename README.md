# RECIVA-Sharpfin-Radio

**Ein lokaler Patchserver + DNS-Proxy für DNT IPdio / Reciva-Internetradios – damit die Geräte auch nach der Reciva-Abschaltung weiterhin Senderlisten, Menüs und Firmware-Updates bekommen.**

> **Status (24.11.2026):** verifiziert auf einer DNT IPdio mit Sharpfin-Firmware.
> Länder und Musikrichtungen laden dynamisch aus lokalen XML-Views:
> **48 Länder / 2.807 Sender + 64 Genres / 4.378 Sender = 7.185 Sender in 121 Views.**
> Die Listen werden paginationweise (30 pro Seite) geladen; Länder- und
> Genre-Pfad sind am Radio getestet. Zusätzlich ist Preset 99 als
> Home-Assistant-Template-Media-Player im Einsatz: RadioBrowser- und
> Music-Assistant-Titel erscheinen als echter Sendername im Sharpfin-Preset
> (siehe [10b](#10b-home-assistant-template-media-player--preset-99)).

---

## Inhaltsverzeichnis

0. [Schnellstart mit dem Deployment-Paket](#0-schnellstart-mit-dem-deployment-paket)
1. [Überblick / Architektur](#1-überblick--architektur)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Docker-macvlan-Netzwerk anlegen](#3-docker-macvlan-netzwerk-anlegen)
4. [Image `reciva-patchserver:latest` bauen](#4-image-reciva-patchserverlatest-bauen)
5. [Patchserver-Container starten](#5-patchserver-container-starten)
6. [DNS-Proxy-Container starten](#6-dns-proxy-container-starten)
7. [Radio einrichten (Netzwerk, Firmware, Sharpfin EP2)](#7-radio-einrichten-netzwerk-firmware-sharpfin-ep2)
8. [Senderdaten: RadioBrowser-Import (auch via Home Assistant)](#8-senderdaten-radiobrowser-import-auch-via-home-assistant)
9. [Pagination-Patch: 30 Sender pro Seite](#9-pagination-patch-30-sender-pro-seite)
10. [Dynamische Menüs & Presets (Sharpfin = Quelle der Wahrheit)](#10-dynamische-menüs--presets-sharpfin--quelle-der-wahrheit)
10a. [Caddy: HTTPS-Streams für den IPdio (HTTP-Relay)](#10a-caddy-https-streams-für-den-ipdio-http-relay)
10b. [Home Assistant Template-Media-Player → Preset 99](#10b-home-assistant-template-media-player--preset-99)
11. [Update, Backup & Rollback](#11-update-backup--rollback)
12. [Fehlerbehebung](#12-fehlerbehebung)
13. [Roadmap](#13-roadmap)
14. [Credits](#14-credits)
15. [Buy me a coffee](#15-buy-me-a-coffee)

---

## 0. Schnellstart mit dem Deployment-Paket

Im Ordner `deploy/` liegt ein fertiges Docker-Compose-Paket. Es baut das Image,
legt das macvlan-Netz an, patched die `server`-Binary mit dem verifizierten
30er-Clamp und startet Patchserver + DNS-Proxy:

```sh
cd deploy
cp .env.example .env
# .env ausfüllen: PARENT_IFACE, IPs, RADIO_IP, DES_KEY, SERIAL ...

./scripts/install.sh
./scripts/verify.sh
```

Enthalten sind die geprüften **Upstream-Artefakte** (`RecivaServer/` mit
`server` + `server.bak-noClamp`, `files/sharpfin-base_0.3_IPdio.patch`, EP2 und
Media-Server-Installer), aber **keine Geheimnisse**. Herkunft, Hashes und
Lizenzhinweise: [`deploy/THIRD_PARTY.md`](deploy/THIRD_PARTY.md). `install.sh`
fasst das Radio nicht an; die Radio-Schritte stehen in
[Abschnitt 7](#7-radio-einrichten-netzwerk-firmware-sharpfin-ep2).
Einzelheiten und Rollback-Hinweise: [`deploy/README.md`](deploy/README.md).

---

## 1. Überblick / Architektur

Das Radio spricht ausschließlich HTTP (kein HTTPS/TLS!). Früher zeigte sein
DNS auf Recivas Server. Da diese abgeschaltet sind, übernimmt ein lokaler
DNS-Proxy die Auflösung der Reciva-Domains und leitet alles andere ganz normal
ins Internet weiter. So funktionieren lokale Senderlisten **und** externe
HTTP-Streams gleichzeitig.

```
Radio (192.168.0.39)
        │  DNS 192.168.0.242
        ▼
reciva-dnsproxy (192.168.0.242, UDP 53)
   ├─ *.reciva.com, *.7803986842.com ──► 192.168.0.240 (Patchserver)
   └─ alles andere ─────────────────────► 192.168.0.1 (Internet/Upstream)
        │
        ▼
reciva-patchserver (192.168.0.240)
   ├─ TCP 80    Reciva-Portal (Challenge/Response, stations.xml, dynamic_menu)
   ├─ TCP 8080  Install-Dateien (Firmware-Patch, EP2, Media-Server, m3u)
   ├─ UDP 123   NTP (ntp.reciva.com → lokale Uhrzeit)
   └─ Xvfb :99  Patchserver-GUI (wird per xdotool automatisch konfiguriert)
```

**Beispiel-IPs dieser Installation** (bitte an das eigene Netz anpassen):

| Dienst | Beispiel-IP | Zweck |
|---|---|---|
| Radio | `192.168.0.39` | DNT IPdio, Firmware `v257-a-865-a-162-c-002` |
| Patchserver | `192.168.0.240` | Portal, Install-Dateien, NTP |
| DNS-Proxy | `192.168.0.242` | Reciva-Domains umleiten, Rest forwarden |
| Gateway / Upstream-DNS | `192.168.0.1` | normales Internet |
| Home Assistant | `192.168.0.50` | RadioBrowser-Integration (Datenquelle, siehe Abschnitt 8) |
| Docker-Host / Portainer | `192.168.0.68:9000` | Container-Verwaltung |

> **Wichtig:** Die Radio-DNS dauerhaft auf den Proxy stellen. Die alte Empfehlung
> „nach dem Patchen auf den Router zurückstellen" ist überholt – dann verschwindet
> die Senderliste wieder.

---

## 2. Voraussetzungen

- Linux-Docker-Host (x86-64) mit nutzbarer macvlan-Unterstützung (hier: Synology NAS).
- Ein freier IP-Bereich im LAN für macvlan-Container.
- Eine eigene Kopie des Patchserver-Pakets `RecivaServer/` (Binary `server`,
  `www8080/`, `stations/`, `patches/`). Das Binary ist nicht Teil dieses Repos –
  es stammt aus der in den Credits genannten Sharpfin/dliw-Patchserver-Welt.
- Radio mit Sharpfin-Firmware; Telnet/FTP-Zugang (Standard `admin` / `<PASSWORT>`).
- **Gerätebezogen und geheim – nie ins Repo schreiben:**
  - Seriennummer des Radios: `<SERIAL>`
  - 8-Byte-DES-Key des Radios: `<DES_KEY>` (siehe Abschnitt 4)
  - Passwörter/Tokens: `<PASSWORT>`, `<HA_TOKEN>`

> **Hinweis zu macvlan:** Container im macvlan sind vom Docker-Host selbst nicht
> erreichbar. Prüfungen bitte von einem anderen Gerät im LAN aus führen (oder
> `docker exec` auf dem Host verwenden).

---

## 3. Docker-macvlan-Netzwerk anlegen

```sh
docker network create -d macvlan \
  --subnet=192.168.0.0/24 \
  --gateway=192.168.0.1 \
  -o parent=<NIC> \
  -o macvlan_mode=bridge \
  reciva-net
```

`<NIC>` ist die physische Schnittstelle des Docker-Hosts (z. B. `eth0`, auf
Synology ggf. `bond0` / `bridge0` – mit `ip link` ermitteln). Die IPs
`.240` und `.242` müssen im LAN frei sein.

---

## 4. Image `reciva-patchserver:latest` bauen

Beide Container nutzen dasselbe Image. Es basiert auf Debian 12 (bookworm).
Die GUI wird in einer virtuellen Anzeige (Xvfb + fluxbox) gestartet und per
`xdotool` automatisch eingestellt.

Build-Kontext (Beispiel):

```
reciva-image/
├── Dockerfile
├── entrypoint.sh
├── configure_gui.sh
├── dnsproxy.py
├── ntp_server.py
└── RecivaServer/        <-- eigene Patchserver-Kopie
```

```dockerfile
FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgtk2.0-0 fonts-dejavu-core xvfb x11-utils xdotool scrot fluxbox \
      python3-minimal ca-certificates libssl3 python3-pil tesseract-ocr \
      at-spi2-core libgail-common python3-pyatspi python3-gi dbus-x11 \
    && ln -sf /usr/lib/x86_64-linux-gnu/libssl.so.3   /usr/lib/x86_64-linux-gnu/libssl.so \
    && ln -sf /usr/lib/x86_64-linux-gnu/libcrypto.so.3 /usr/lib/x86_64-linux-gnu/libcrypto.so \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/RecivaServer
COPY RecivaServer/ /opt/RecivaServer/
COPY entrypoint.sh /entrypoint.sh
COPY configure_gui.sh /opt/configure_gui.sh
COPY dnsproxy.py /opt/dnsproxy.py
COPY ntp_server.py /opt/ntp_server.py
RUN chmod +x /entrypoint.sh /opt/configure_gui.sh /opt/dnsproxy.py /opt/RecivaServer/server

EXPOSE 80/tcp 443/tcp 8080/tcp 53/udp 123/udp
ENTRYPOINT ["/entrypoint.sh"]
```

```sh
docker build -t reciva-patchserver:latest .
```

### 4.1 DES-Key des Radios ermitteln (einmalig, gerätebezogen)

Das Reciva-Portal authentifiziert das Radio per Challenge–Response:
Das Radio sendet eine DES-CBC-verschlüsselte Anfrage (IV `bde73266b946f3ab`),
der Server antwortet mit dem **individuellen DES-Key des Radios**. Wer hier
`0000000000000000` stehen hat, sieht am Radio „Kein Internet".

Den Key mit dliw's `sread` (ARM-Binary aus den Credits) vom Radio lesen:

```sh
# per Telnet auf dem Radio:
killall sernum; /usr/bin/sernum --daemon
/tmp/sread -c 0000000000000000
# Null-Challenge -> erwartete Antwort: 462528ce4d91403f
# daraus den 8-Byte-Key ableiten und als <DES_KEY> bezeichnen
```

Diese Firmware nutzt **DES, nicht AES** (andere Firmwares nutzen AES – die
AES-Teile der `reciva_decrypt.py` gelten hier nicht).

### 4.2 `configure_gui.sh` (Auszug – `<DES_KEY>` einsetzen)

Das Skript wartet auf das Fenster `Reciva Server`, setzt den DNS-Server,
aktiviert „Provide patch" + „Full server", wählt die Patchdatei und trägt
den DES-Key ein. Die Koordinaten beziehen sich auf 1024×768:

```sh
#!/bin/sh
set -u
export DISPLAY=:99
W=""
i=0
while [ "$i" -lt 60 ]; do
  W="$(xdotool search --name 'Reciva Server' 2>/dev/null | head -1)"
  [ -n "$W" ] && break
  i=$((i + 1)); sleep 0.5
done
[ -z "$W" ] && { echo "configure_gui: no window"; exit 1; }
xdotool windowactivate "$W" 2>/dev/null || true
sleep 0.5

click() { xdotool mousemove --window "$W" "$1" "$2" click 1; sleep 0.2; }

click 300 38                       # DNS server
xdotool key --window "$W" ctrl+a
xdotool type --window "$W" --delay 15 '192.168.0.1'

click 18 157                       # "Provide patch" (falls nicht aktiv)
sleep 2
click 50 184                       # Patch-Datei-Radio
click 400 187                      # Combo: erstes Element wählen
xdotool key --window "$W" alt+Down
sleep 0.4
xdotool key --window "$W" Home
xdotool key --window "$W" Return

click 18 344                       # "Full server" (falls nicht aktiv)

click 200 292                      # EKey / DES-Key
xdotool key --window "$W" ctrl+a
xdotool type --window "$W" --delay 15 '<DES_KEY>'

click 286 455                      # "Start session"
echo "configure_gui: done"
```

Vor dem Bauen `configure_gui.sh` mit dem echten Key versehen; eine Kopie ohne
Key (`configure_gui.sh.bak-zerokey`) aufbewahren. Nach Installation der IPdio-
Patchdatei (Abschnitt 7.2) die Datei
`/opt/RecivaServer/patches/base_0.3.patch` ersetzen.

<details>
<summary><code>entrypoint.sh</code> (vollständig)</summary>

```sh
#!/bin/sh
set -e
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
```

`sync_sharpfin_menu.py` ist optional, aber für die dynamischen Menüs nötig
(Abschnitt 10). Es liegt im Patchserver unter `/opt/sync_sharpfin_menu.py`.
</details>

<details>
<summary><code>dnsproxy.py</code> (vollständig, minimal)</summary>

```python
#!/usr/bin/env python3
"""DNS-Proxy: Reciva-Domains -> Patchserver, alles andere -> Upstream."""
import socket, struct

LISTEN = ("0.0.0.0", 53)
UPSTREAM = ("192.168.0.1", 53)      # an das eigene Netz anpassen
LOCAL_A = "192.168.0.240"           # Patchserver-IP
SUFFIX = ".7803986842.com"
RECIVA_SUFFIX = ".reciva.com"


def parse_question(data):
    qd = struct.unpack("!H", data[4:6])[0]
    if len(data) < 12 or qd < 1:
        raise ValueError("short dns packet")
    off, labels = 12, []
    while True:
        n = data[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0:
            raise ValueError("compressed question")
        off += 1
        labels.append(data[off:off + n].decode("ascii", "ignore"))
        off += n
    qtype, qclass = struct.unpack("!HH", data[off:off + 4])
    return ".".join(labels).lower(), qtype, off + 4


def response(data, off, qtype, local):
    question = data[12:off]
    header_id = data[:2]
    if qtype == 1 and local:  # A-Record -> Patchserver
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + socket.inet_aton(LOCAL_A)
        return header_id + b"\x81\x80" + struct.pack("!HHHH", 1, 1, 0, 0) + question + answer
    return header_id + b"\x81\x80" + struct.pack("!HHHH", 1, 0, 0, 0) + question


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(LISTEN)
    while True:
        data, addr = s.recvfrom(2048)
        try:
            name, qtype, off = parse_question(data)
            if (name == SUFFIX[1:] or name.endswith(SUFFIX)
                    or name == RECIVA_SUFFIX[1:] or name.endswith(RECIVA_SUFFIX)):
                s.sendto(response(data, off, qtype, True), addr)
                continue
        except Exception:
            pass
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.settimeout(3.0)
            u.sendto(data, UPSTREAM)
            reply, _ = u.recvfrom(4096)
            u.close()
            s.sendto(reply, addr)
        except Exception:
            fail = data[:2] + b"\x81\x82" + struct.pack("!HHHH", 1, 0, 0, 0) + data[12:]
            s.sendto(fail, addr)


if __name__ == "__main__":
    main()
```
</details>

<details>
<summary><code>ntp_server.py</code> (vollständig)</summary>

```python
#!/usr/bin/env python3
"""Minimaler NTPv4-Server: ntp.reciva.com -> lokale Zeit."""
import socket, struct, time

OFFSET = 2208988800
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", 123))

def ntp_time(t):
    sec = int(t) + OFFSET
    return (sec << 32) | int((t - int(t)) * 2**32)

while True:
    try:
        req, addr = sock.recvfrom(1024)
        if len(req) < 48:
            continue
        ver = (req[0] >> 3) & 0x07
        now = time.time()
        reply = struct.pack("!BBBBIIIQQQQ", (min(ver, 4) << 3) | 4, 2, 6, 0xEC,
                            0, 0, 0x7F7F0100,
                            ntp_time(now - 1), struct.unpack("!Q", req[40:48])[0],
                            ntp_time(now), ntp_time(now))
        sock.sendto(reply, addr)
    except Exception:
        pass
```
</details>

---

## 5. Patchserver-Container starten

```sh
docker run -d \
  --name reciva-patchserver \
  --network reciva-net \
  --ip 192.168.0.240 \
  --restart unless-stopped \
  reciva-patchserver:latest
```

Dienste im Container:

| Port | Dienst |
|---|---|
| TCP 80 | Reciva-Portal (Session, `stations.xml`, `dynamic_menu`) |
| TCP 8080 | Install-/Datei-Server (Firmware-Patches, EP2, m3u) |
| UDP 123 | NTP |

**Firmware-Patch für die DNT IPdio:** Der generische `sharpfin-base_0.3.patch`
führt bei der IPdio nicht zum Ziel. Stattdessen die IPdio-Variante
`sharpfin-base_0.3_IPdio.patch` (MD5 `043934970007ed0e83ad62ecb8d54b02`,
204.896 B) verwenden. Sie liegt jetzt unter
[`deploy/files/sharpfin-base_0.3_IPdio.patch`](deploy/files/sharpfin-base_0.3_IPdio.patch);
`./scripts/install.sh` legt sie automatisch an ihren Build-Platz. Das Original
vorher sichern und die Datei als `/opt/RecivaServer/patches/base_0.3.patch`
ablegen. Als Quelle für die IPdio-spezifischen Patches diente
https://github.com/jisotalo/reciva-radio-patching (siehe
[`THIRD_PARTY.md`](deploy/THIRD_PARTY.md)):

```sh
docker cp deploy/files/sharpfin-base_0.3_IPdio.patch \
  reciva-patchserver:/opt/RecivaServer/patches/base_0.3.patch
# Gegenprobe (liefert genau diese MD5):
curl -s http://192.168.0.240/file/reciva-upgrade.tar.bz2 | md5sum
```

Der Server liest die Datei pro Request – ein Neustart ist dafür nicht nötig.

---

## 6. DNS-Proxy-Container starten

```sh
docker run -d \
  --name reciva-dnsproxy \
  --network reciva-net \
  --ip 192.168.0.242 \
  --restart unless-stopped \
  --entrypoint python3 \
  reciva-patchserver:latest -u /opt/dnsproxy.py
```

 Prüfen (von einem LAN-Gerät):

```sh
nslookup www.reciva.com 192.168.0.242   # -> 192.168.0.240
nslookup example.com    192.168.0.242   # -> normale Internet-Auflösung
```

---

## 7. Radio einrichten (Netzwerk, Firmware, Sharpfin EP2)

### 7.1 Netzwerk am Radio

`Menü → Configure → Network Config → Edit Config`:

- DHCP aus
- IP: freie Adresse, z. B. `192.168.0.39`, Netmask `255.255.255.0`
- Gateway `192.168.0.1`
- **DNS 1: `192.168.0.242`**, DNS 2: leer – dauerhaft so lassen!

Danach das Radio einmal komplett vom Strom trennen und neu starten.

### 7.2 Firmware-Patch installieren

1. `Menü → Configure → Upgrade Firmware` → **YES**
2. Das Radio lädt den Patch vom lokalen Patchserver („Patching / Do not unplug").
   Wenn nur ein Reboot passiert: Schritt 1 erneut versuchen.
3. Nach dem Reboot die IP wieder auf DHCP stellen (DNS auf den Proxy lassen).
4. Sharpfin-UI: `http://<RADIO-IP>/`, Telnet/FTP: `admin` / `<PASSWORT>`.

### 7.3 Sharpfin EP2 (Addon – nicht über „Upgrade Firmware"!)

EP2 ist ein Addon für die Sharpfin-Weboberfläche, **keine Firmware**. Der
Reciva-Weg meldet sonst „not enough space".

- Vorher ggf. Speicher freimachen (ungenutzte Kernelmodule entfernen):

```sh
mount / -orw,remount
rm -f /lib/modules/2.4.26-vrs1-bast2/zd1211b-driver.o \
      /lib/modules/2.4.26-vrs1-bast2/zd1211-driver.o \
      /lib/modules/2.4.26-vrs1-bast2/reciva_font_japanese.o
mount / -oro,remount
```

- In der Sharpfin-UI: `Install → Install Addon` → URL:

```
http://192.168.0.240:8080/sharpfin-ep2.install
```

Nach Download/Readme auf *Click Here to Do the Install* klicken; das Radio
rebootet automatisch. Installiert wurden u. a. `sharpfin-www_0.7`,
`sharpfin-ftpd_0.1`, `sharpfin-lircd_0.1`.

**Optionaler Fallback:** Sharpfin Media Server 1.0
(`http://192.168.0.240:8080/media-server-1.0.install`) stellt Sender über
`Media Player → UPnP Servers` bereit (`ushare`, nur lokal im Radio). Der
Hauptweg ist aber das normale `Sender`-Menü über den Patchserver.

> **Playlist-Regeln für das Radio:** ≤300 kB pro Liste (besser ≤50 Tracks),
> nur `http://`-Streams (kein HTTPS!), Verzeichnisnamen ASCII-only.
> FTP-`STOR` schneidet bestehende Dateien **nicht** ab → vor Upload löschen.

---

## 8. Senderdaten: RadioBrowser-Import (auch via Home Assistant)

### 8.1 Woher die Daten kommen

Die Sender stammen aus **RadioBrowser** – zum einen aus der
**Home-Assistant-Integration „Radio Browser"** (`media-source://radio_browser`,
hier auf HA `192.168.0.50`), zum anderen direkt aus der öffentlichen
Radio-Browser-API für den Massenimport. HA diente als Quelle und Kontrollinstanz
für Favoriten/Stream-URLs; für die ~7.000 Sender ist der direkte API-Export
nötig, weil die HA-UI keine Massenabfrage bietet.

> **Geplant:** Eine echte Home-Assistant-Integration (Automatisierung /
> Custom Component), die den Import direkt aus HA auslöst, soll später folgen
> (siehe [Roadmap](#13-roadmap)). Sie ist **noch nicht** Teil dieses Repos.

### 8.2 Abfrage (Filter)

```text
GET https://de1.api.radio-browser.info/json/stations/search
    ?countrycode=DE&codec=MP3&hidebroken=true
    &order=votes&reverse=true&limit=500
```

Für Genres statt `countrycode` der Parameter `tag=<tag>` (z. B. `rock`,
`80s`, `jazz`). Danach:

1. nur `http://`-URLs behalten (HTTPS kann die Firmware nicht),
2. doppelte URLs entfernen,
3. maximal **100** pro Land/Genre (absteigend nach Votes),
4. Titel ASCII-sicher machen (Umlaute auflösen, Steuerzeichen entfernen).

Aus den Ergebnissen werden M3U-Dateien und daraus Reciva-XML-Views gebaut:

```
/opt/RecivaServer/stations/views/view_<location>_<genre>_<language>.xml
```

Jeder View enthält einen `<view>`-Block mit den Station-IDs und einen
`<station-list>`-Block mit `<version>4029</version>`, `<streamtype>1</streamtype>`,
`<codec>MP3</codec>`, `<protocol>http</protocol>`. In `stations.xml` stehen die
passenden `<count>112,0,100</count>`-Einträge (Location, Genre, Anzahl).

### 8.3 Import-Stand

| Import | Umfang | IDs | Views |
|---|---|---|---|
| Länder | 48 Länder, 2.807 Sender (18 davon exakt 100) | `100001–102807` | `view_<loc>_0_0.xml` |
| Genres | 64 Genres, 4.378 Sender | `2000001–2004378` | `view_0_<genre>_0.xml` |

Länder: Europa + England/UK + USA + Australien. AD, LI und VA haben keine
HTTP-MP3-Station. Genres: RadioBrowser-Tags auf die vorhandenen 65 Reciva-Genre-IDs
gemappt (z. B. `rock→40`, `80s→6`); „Unknown" (45) hat keinen Tag.
Beispiele: Deutschland `112,0,100`, Rock `0,40,100`, 80er `0,6,100`.

Radio-Pfade: `Sender → Länder → <Land>` und `Sender → Musikrichtung → <Genre>`.
**Nach einem neuen Import die neue `stations.xml` mit dem Power-Button
neu starten** – sonst zeigt das Menü noch den gecachten alten Stand (z. B. nur
„Varied" unter Musikrichtung).

### 8.4 Skripte

Die Generator-Skripte liegen lokal (`build_radiobrowser_100.py`,
`build_reciva_views_100.py`, `build_radiobrowser_genres.py`,
`build_reciva_genres.py`) und können als Vorlage für eigene Importe dienen:
API-Abfrage → M3U → Reciva-View → `tar` nach
`/opt/RecivaServer/stations/` → Pagination prüfen → Radio neu starten.

---

## 9. Pagination-Patch: 30 Sender pro Seite

Die Firmware fragt Listen in Seiten an:

```
/portal-newformat/stations.xml?request_view=112_0_0&view_type=stations_only&start=0&count=30
```

Die Firmware erhöht `start` um 30 (`view_manager.c`), der Original-Patchserver
liefert bei fehlendem/großem `count` aber die **komplette** Liste (z. B. 51 kB
für 100 Sender) – das Radio blieb bei „Lade Senderliste" hängen und rebootete.
Deshalb wurde das Binary serverseitig gepatcht: `stations_only` wird jetzt auf
max. **30 Details pro Antwort** begrenzt.

Gegenprobe (passiv am Patchserver, Deutschland):

```sh
# im Container: python3 - (Auszug)
# request_view=112_0_0&view_type=stations_only&start=0/30/60/90&count=30
# -> 30 / 30 / 30 / 10 Details
```

Beim Radio lädt die 100er-Liste beim Scrollen nach und endet mit normalem
Wrap-around. **Original-Binary vorher sichern** (`server.bak-noClamp`);
bei Problemen damit zurückrollen. Der Patch ist Teil des hier beschriebenen
Images – eine öffentliche Konfigurationsoption dafür gibt es nicht (dliw hat
den Quellcode nie veröffentlicht, siehe Credits).

---

## 10. Dynamische Menüs & Presets (Sharpfin = Quelle der Wahrheit)

### 10.1 „Meine Sender / Meine Streams"

Die deutsche UI nennt `My Stuff` → **„Meine Favoriten"**:
`Sender → Meine Favoriten → Meine Sender / Meine Streams / Mein Podcast / Mein Verlauf`.

- Der Radio-Request ist
  `POST /portal-newformat/dynamic_menu?serial=<SERIAL>` mit `dmenuid=<id>` im
  Body (oder `GET ...?dmenuid=<id>`). **Nicht** `id`/`menu_id` verwenden.
- Der Patchserver liest daraus `stations/dynamic/menu_<id>.xml`:
  - `20009` = Meine Sender (alle Presets)
  - `200011` = Meine Streams (nur `.m3u`/`.m3u8`)
  - `200014` = Mein Podcast – **bleibt der originale Platzhalter, nicht antasten**
  - `200059` = DAR.FM; `HISTORY` lokal aus `/mnt/config/PRE_history.xml`
- Für `20009`/`200011` in `stations.xml` und
  `/mnt/config/SLR_TopLevelMenuCache.xml` `scope="nocache"` setzen.
- Der Sync-Daemon `/opt/sync_sharpfin_menu.py` liest alle 5 s den
  Sharpfin-Preset-Manager aus und schreibt die Menü-XMLs. Log:
  `/tmp/sync_sharpfin.log`. Der Preset-Manager liefert Name **und** URL;
  abgefragt werden die Plätze 1–20, damit neue Presets automatisch erscheinen.

### 10.2 Goldene Regel: nur die Sharpfin-UI schreibt Presets

**Nie** `preset*.xml` direkt auf dem Radio überschreiben. Store/Edit/Delete
ausschließlich über die Sharpfin-CGIs
(`radio_Presets_Store.cgi`, `Presets_edit.cgi`, `control_Presets.cgi`).
Deren Originale schrieben eine kaputte Minimal-XML mit `<station id='3508'>` –
die Firmware spielte dann „Sandisc" statt der gespeicherten URL. Die reparierte
Variante schreibt volle, gültige XML mit eigener Station-ID (`100+Platz`),
Stream-ID (`900+Platz`), `<version>`, `<protocol>`, `<metadata>`, `<locations>`.

Weitere Firmware-Eigenheiten:

- `preset0.xml` ist der einmalige Resume-Slot des Radios – **nicht manuell belegen**.
- Die echten Presets sind `preset1.xml` … `preset6.xml` (Tasten 1–6).
- Radio liest die Datei beim Tastendruck; Änderungen wirken ohne Reboot.
- Bei bestehendem Platz zuerst „Preset N already exists", dann zusätzlich
  „**Confim**" (Original-Tippfehler!) klicken.
- Keine IR-Simulation als Lösung einsetzen – die Daten müssen dynamisch aus
  der Datenbank/UI kommen.

---

## 10a. Caddy: HTTPS-Streams für den IPdio (HTTP-Relay)

Der IPdio kann selbst **kein TLS**. Ein HTTPS-Stream muss deshalb außerhalb des
Radios terminiert werden. Caddy übernimmt das: Er holt den Stream per HTTPS vom
Upstream und liefert ihn dem Radio als reines HTTP aus. Das Radio startet also
weiterhin nur eine HTTP-Anfrage – Caddy „wandelt" nicht die Anfrage des Radios,
sondern die Antwort des Upstreams. Getestet mit Caddy 2.11.4 im LAN.

### 10a.1 Caddy installieren / Port ergänzen

Wenn Caddy bereits läuft, genügt es, den Port `8082` zu veröffentlichen und die
Caddyfile aus 10a.2 zu ergänzen. Bestehende Container **nicht** blind ersetzen –
Ports, Mounts, Netzwerk und Restart-Policy beibehalten.

Für eine neue Installation z. B.:

```sh
docker run -d --name caddy \
  --restart unless-stopped \
  -p 80:80 -p 443:443 -p 8082:8082 \
  -v /pfad/zu/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v caddy_data:/data \
  -v caddy_config:/config \
  caddy:2-alpine \
  caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
```

Danach prüfen und aktiv machen:

```sh
docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

### 10a.2 Caddyfile-Snippet

```caddyfile
:8082 {
	@https path_regexp t ^/https/([^/]+)/(.*)$
	handle @https {
		map {http.regexp.t.1} {upstream_https} {
			~^([^:]+:[0-9]+)$ $1
			~^([^:]+)$ $1:443
		}
		uri strip_prefix /https/{http.regexp.t.1}
		reverse_proxy {upstream_https} {
			header_down Location "https://" "http://192.168.0.68:8082/https/"
			header_down Location "^/" "http://192.168.0.68:8082/https/"
			transport http {
				tls
			}
			header_up Host {http.regexp.t.1}
		}
	}

	@http path_regexp u ^/http/([^/]+)/(.*)$
	handle @http {
		map {http.regexp.u.1} {upstream_http} {
			~^([^:]+:[0-9]+)$ $1
			~^([^:]+)$ $1:80
		}
		uri strip_prefix /http/{http.regexp.u.1}
		reverse_proxy {upstream_http} {
			header_down Location "https://" "http://192.168.0.68:8082/https/"
			header_down Location "http://" "http://192.168.0.68:8082/http/"
			header_down Location "^/" "http://192.168.0.68:8082/http/"
			header_up Host {http.regexp.u.1}
		}
	}

	handle {
		respond 404
	}
}
```

Das `map` ergänzt fehlende Ports: HTTPS ohne Port → `443`, HTTP ohne Port → `80`.
Ohne dieses `map` dialt Caddy auf Port `0` und liefert `502`.

Die `header_down Location`-Regeln schreiben Redirects des Upstreams auf den
eigenen Relay zurück. Das ist wichtig für RadioBrowser-URLs wie
`https://stream.example.de/...`, die mit `302` auf einen anderen HTTPS-Host
umleiten – der IPdio könnte dem Redirect sonst nicht folgen.

Falls das Upstream-Zertifikat nicht verifiziert werden kann, im `transport http`
des HTTPS-Blocks ergänzen:

```caddyfile
tls_insecure_skip_verify
```

Nur im Notfall verwenden – korrekte Zertifikate sind vorzuziehen.

### 10a.3 Preset-URLs umschreiben

Der Vorspann für HTTPS-Ziele ist:

```text
http://192.168.0.68:8082/https/
```

Regel:

```text
https://X  →  http://192.168.0.68:8082/https/X
http://X   →  http://192.168.0.68:8082/http/X
```

Dabei ist `X = host[:port]/pfad?query`. Subdomains funktionieren ohne weitere
Anpassung, z. B. `stream.domain.de`. **Wichtig:** Hat die URL keinen Pfad, muss
ein `/` angehängt werden – sonst trifft die Route nicht zu (`404`).

Beispiele:

```text
https://dogglounge.com:8000/;?type=http
→ http://192.168.0.68:8082/https/dogglounge.com:8000/;?type=http

http://musik.schlagerparadies.de:30842/
→ http://192.168.0.68:8082/http/musik.schlagerparadies.de:30842/

https://stream.epic-lounge.com/ibiza-chillout-lounge?ref=radiobrowser
→ http://192.168.0.68:8082/https/stream.epic-lounge.com/ibiza-chillout-lounge?ref=radiobrowser
```

Diese URLs werden weiterhin **ausschließlich über die Sharpfin-UI** in die
Presets eingetragen (siehe 10.2). Caddy schreibt keine `preset*.xml`.
Der DNS-Proxy aus Abschnitt 6 ist hier nicht beteiligt, weil die IP direkt
eingetragen wird.

### 10a.4 Funktionstest

```sh
curl -I 'http://192.168.0.68:8082/https/dogglounge.com:8000/;?type=http'
# HTTP/1.1 200 OK
# Content-Type: audio/mpeg
# Icy-Name: Dogglounge Deep House Radio
```

> **Sicherheit:** Der Endpunkt ist LAN-only und kann grundsätzlich beliebige,
> aus dem Caddy-Netz erreichbare Hosts proxyen. Port `8082` nicht ins Internet
> veröffentlichen.

---

## 10b. Home Assistant Template-Media-Player → Preset 99

Seit 24.11.2026 ist Preset 99 zusätzlich über einen **Template-Media-Player**
in Home Assistant erreichbar. Damit lassen sich Sender aus RadioBrowser oder
aus Music Assistant in den Sharpfin-Preset 99 „pushen“. Verifiziert wurde der
komplette Weg inklusive hörbarem Audio am Radio.

> **Grundregel:** Auch dieser Weg schreibt niemals direkt `preset*.xml`.
> Der einzige Schreiber bleibt die Sharpfin-Oberfläche, konkret
> `Presets_edit.cgi?...&place=99&action=program`.

> **YAML-Hinweis:** Alle folgenden Blöcke sind Auszüge. Sie müssen in die
> bereits vorhandenen Top-Level-Blöcke `template:`, `rest_command:`,
> `input_text:` und `rest:` der `configuration.yaml` **eingefügt** werden.
> Keine doppelten Top-Level-Keys erzeugen und keinen neuen `script:`-Block
> anlegen (in dieser Installation existiert bereits `script: !include
> scripts.yaml`).

### 10b.1 Warum ein Template-Player

Der IPdio hat selbst keine HA-Integration. Stattdessen wird in der
`configuration.yaml` ein Template-Entity angelegt:

```yaml
template:
  - media_player:
      - name: "IPdio Preset 99"
        default_entity_id: media_player.ipdio_preset99
        unique_id: ipdio_preset99
        icon: mdi:radio
        state: "idle"
        optimistic: true          # HA nimmt Befehle sofort an
        device_class: speaker
        play_media:               # einzig unterstützter Befehl
          - ...                   # Namen/URL auflösen (siehe unten)
          - action: rest_command.ipdio_preset99_store
          - delay: "00:00:01"
          - action: rest_command.ipdio_preset99_play
```

Wichtig:

- `optimistic: true` / `assumed_state: true`: Der HA-Status springt sofort auf
  `playing`, **auch wenn das Radio gerade still ist**. HA ist hier kein
  Wiedergabemonitor.
- `supported_features: 512` = nur `PLAY_MEDIA`. Es gibt bewusst kein
  `media_stop`; ein Stopp erfolgt am Radio oder über die Sharpfin-UI.
- Der echte Sende-Start läuft über `rest_command.ipdio_preset99_play` →
  `Presets_play.cgi?i=99`. Auto-Play ist in dieser Installation nach
  ausdrücklicher Freigabe aktiv; in anderen Setup bitte erst freigeben.

Die zwei REST-Commands sind denkbar einfach:

```yaml
rest_command:
  ipdio_preset99_store:
    url: >-
      http://192.168.0.39/cgi-bin/Presets_edit.cgi?name={{ preset_name | urlencode }}
      &url={{ preset_url | urlencode }}&place=99&action=program
  ipdio_preset99_play:
    url: "http://192.168.0.39/cgi-bin/Presets_play.cgi?i=99"
```

`preset_url` ist immer eine Caddy-Relay-URL aus [10a](#10a-caddy-https-streams-für-den-ipdio-http-relay):

```text
https://X  →  http://192.168.0.68:8082/https/X
http://X   →  http://192.168.0.68:8082/http/X
```

### 10b.2 RadioBrowser-Sendertitel auflösen

Es gibt mehrere Wege, einen Sendernamen zu bekommen. Alle münden im selben
`preset_name`-Feld; die Priorität ist:

1. **RadioBrowser direkt aus HA:** `media-source://radio_browser/<UUID>`
   → Helper `input_text.ipdio_rb_uuid` → REST-Sensor
   `sensor.ipdio_radiobrowser_name`.
2. **Music Assistant:** MA ruft `play_media` mit `extra.metadata.title` auf.
3. **MA-Radio mit `no name`:** MA legt Radiosender oft als
   `builtin://radio/<URL>` an und schickt wörtlich `no name`. Dann wird die
   Original-URL aus `state_attr('media_player.ipdio_preset_99',
   'media_content_id')` geholt, in `input_text.ipdio_rb_stream_url`
   geschrieben und über RadioBrowser `/json/stations/byurl` aufgelöst.
4. **Fallback:** Host aus der Stream-URL (z. B. `192.168.0.50:8097`).

Werte wie `''`, `none`, `unknown`, `unavailable`, `no name`, `no_name` und
`n/a` werden als „kein Name" behandelt. Der Resultat-Name wird auf
**40 Zeichen** gekürzt – das ist die Feldbreite des Sharpfin-Formulars.

Die zugehörigen REST-Sensoren (Auszug):

```yaml
input_text:
  ipdio_rb_uuid:
    name: "IPdio RadioBrowser UUID"
    max: 64
    initial: "<STATION_UUID>"
  ipdio_rb_stream_url:
    name: "IPdio RadioBrowser Stream URL"
    max: 255
    initial: ""

rest:
  - resource_template: >-
      https://de1.api.radio-browser.info/json/stations/byuuid/{{ states('input_text.ipdio_rb_uuid') }}
    scan_interval: 3600
    sensor:
      - name: "IPdio RadioBrowser URL"
        value_template: "{{ value_json[0].url_resolved or value_json[0].url }}"
      - name: "IPdio RadioBrowser Name"
        value_template: "{{ value_json[0].name }}"
  - resource_template: >-
      https://de1.api.radio-browser.info/json/stations/byurl?url={{ states('input_text.ipdio_rb_stream_url') | urlencode }}
    scan_interval: 3600
    sensor:
      - name: "IPdio RadioBrowser Name by URL"
        value_template: "{{ value_json[0].name if value_json | length > 0 else '' }}"
```

> **Falle:** Der Entity-ID des zweiten Sensors lautet
> `sensor.ipdio_radiobrowser_name_by_url` (vom *Namen* abgeleitet), nicht
> `sensor.ipdio_radiobrowser_byurl_name` (das ist nur die `unique_id`).

Der Namens-Block im `play_media`-Ablauf entspricht vereinfacht:

```jinja
{% set bad = ['', 'none', 'unknown', 'unavailable', 'no name', 'no_name', 'n/a'] %}
{% if media_content_id.startswith('media-source://radio_browser/') %}
  {% set name = states('sensor.ipdio_radiobrowser_name') %}
{% else %}
  {% set title = '' %}
  {% if extra is defined and extra is mapping %}
    {% if extra.get('metadata') is mapping %}
      {% set title = extra.get('metadata', {}).get('title') or '' %}
    {% endif %}
    {% if (title | string | trim | lower) in bad %}
      {% set title = extra.get('title') or '' %}
    {% endif %}
  {% endif %}
  {% if (title | string | trim | lower) not in bad %}
    {% set name = title %}
  {% elif states('sensor.ipdio_radiobrowser_name_by_url') | lower not in bad %}
    {% set name = states('sensor.ipdio_radiobrowser_name_by_url') %}
  {% else %}
    {% set name = 'Host aus der URL' %}
  {% endif %}
{% endif %}
{{ (name | replace('\n', ' ') | replace('\r', ' ') | trim)[:40] }}
```

Vor dem Store werden die Sensoren mit `homeassistant.update_entity`
aktualisiert; ein kurzes `delay` sorgt dafür, dass der neue Wert auch im
`preset_name` ankommt.

### 10b.3 Music Assistant details

`192.168.0.50:8097` ist der **Music-Assistant-Streamserver**. Er liefert nur
Audio; die `/info`-Antwort enthält lediglich eine `server_id`. Der Sendername
steckt nicht in der Stream-URL, sondern im `play_media`-Aufruf bzw. im
RadioBrowser-API. Der MA-Player muss einmalig unter
*Settings → Player Providers → Home Assistant Media Players* importiert werden.

Live-verifizierte Beispiele:

```text
RadioBrowser (UUID)      → Epic Lounge - IBIZA CHILLOUT LOUNGE
MA mit Metadaten         → Lane 8 Summer 2016 Mixtape
MA mit "no name"         → 0R - CLASSICAL HOTEL LOUNGE - CLASSICAL
```

Zum Prüfen des Presets **niemals** `Presets_edit.cgi` ohne `name`/`url`
aufrufen (das speichert ein leeres Preset), sondern lesend:

```sh
curl -s 'http://192.168.0.39/cgi-bin/radio_Presets_Manage.cgi?start=99&end=99&action=program'
```

Bekannte Eigenheiten: harmlose doppelte `unique_id`-Warnungen der
REST-Sensoren im HA-Log und der fehlende `media_stop` des Template-Players.
Beides beeinträchtigt den Preset-99-Weg nicht.

---

## 11. Update, Backup & Rollback

Alle Änderungen an `stations/` **vorher sichern**:

```sh
docker exec reciva-patchserver sh -c \
  'cd /opt/RecivaServer && tar czf stations.bak-$(date +%Y%m%d-%H%M%S).tar.gz stations'
```

Rollback (Beispiel):

```sh
docker exec reciva-patchserver sh -c \
  'cd /opt/RecivaServer && rm -rf stations && tar xzf stations.bak-<ZEITSTEMPEL>.tar.gz'
# danach Radio per Power-Button neu starten
```

Weitere Backups dieser Installation:

- `server.bak-noClamp` – Original-Binary ohne 30er-Clamp
- `stations.bak-before100-*.tar.gz` – vor dem Länder-Großimport
- `stations.bak-beforeGenre-*.tar.gz` – vor dem Genre-Import
- `configure_gui.sh.bak-zerokey` – GUI-Skript ohne DES-Key

Nach Container-Neuerstellung Dateien zurückkopieren (Beispiel Patchdatei):

```sh
docker cp deploy/files/sharpfin-base_0.3_IPdio.patch \
  reciva-patchserver:/opt/RecivaServer/patches/base_0.3.patch
```

---

## 12. Fehlerbehebung

| Symptom | Ursache / Lösung |
|---|---|
| Radio: „Kein Internet" / Session-Fehler | Falscher DES-Key in `configure_gui.sh`; mit `sread` neu auslesen |
| „Lade Senderliste" bleibt hängen, Reboot | Patchserver ohne 30er-Clamp liefert 51 kB am Stück → gepatchtes Binary einsetzen |
| Unter „Musikrichtung" steht nur „Varied" | Radio hat neue `stations.xml` gecacht → **Power-Button**-Reboot |
| Senderliste leer nach Reboot | Radio-DNS zeigt nicht auf `.242`; dauerhaft auf den Proxy stellen |
| Externe Streams gehen nicht | Direkt nur `http://`; HTTPS über den Caddy-Relay aus [10a](#10a-caddy-https-streams-für-den-ipdio-http-relay) |
| MAC-Container vom NAS nicht erreichbar | Normal bei macvlan – von einem LAN-Gerät oder per `docker exec` testen |
| Radio-Uhr falsch | NTP-Prozess prüfen: `docker logs reciva-patchserver`, UDP 123 frei? |
| Preset spielt falschen Sender („Sandisc") | ID-Kollision / alte Minimal-XML → Preset über Sharpfin-UI neu speichern |
| Radio crash loop | Zu große m3u (≥~4000 Tracks / 560 kB) → ≤50 Tracks, vor Upload löschen |

---

## 13. Roadmap

- [ ] **Vollständige Home-Assistant-Integration:** Der RadioBrowser-Import soll
      künftig direkt aus HA heraus auslösbar sein (Service/Automation bzw.
      Custom Component inkl. `HA_TOKEN`-basierter API-Anbindung). Die CSV-/M3U-
      Generatoren und Reciva-View-Builder dafür liegen bereits bereit. Diese
      Integration ist **weiterhin nicht** Teil dieses Repos.
- [ ] Optional: automatische Aktualisierung der Senderlisten (z. B. wöchentlich).
- [x] HTTPS-Streams über einen lokalen Caddy-HTTP-Relay – siehe [10a](#10a-caddy-https-streams-für-den-ipdio-http-relay). Keine Firmware-Anpassung nötig.
- [x] Preset-99-Push aus HA über einen Template-Media-Player, inklusive
      RadioBrowser- und Music-Assistant-Sendertiteln – siehe
      [10b](#10b-home-assistant-template-media-player--preset-99). Dies ist eine
      HA-Konfiguration und keine eigene Custom Component.

---

## 14. Credits

- **Sharpfin** und die Community – für die Firmware-Patches, EP2 und die
  Web-Oberfläche, ohne die das Radio nicht mehr nutzbar wäre. Deren
  Originalartefakte liegen jetzt unter [`deploy/THIRD_PARTY.md`](deploy/THIRD_PARTY.md).
- **dliw** – für den Patchserver, `sread`/Entschlüsselungs-Tools und die
  Reverse-Engineering-Arbeiten an der Firmware. Auch dessen `server`-Binary ist
  dort mit Prüfsummen dokumentiert.
- **opencode – Big Pickle** – für Recherche, Reverse Engineering, Skripte,
  Deployments, Tests und diese Dokumentation.
- **Home Assistant** und die RadioBrowser-Integration – Datenquelle und
  Kontrollinstanz für die Senderimporte sowie der Template-Media-Player für
  Preset 99.
- **Music Assistant** – liefert Metadaten (Sendertitel) und den lokalen
  Streamserver auf Port `8097`.
- **RadioBrowser** – die offene Senderdatenbank (API & Community), auch für die
  Namensauflösung per UUID bzw. Stream-URL.

Nützliche Seiten, die bei der Recherche geholfen haben:

- https://www.sharpf.in/ – Sharpfin-Wiki (Firmware, Login, Menüs)
- https://www.megapico.co.uk/sharpfin/ – Sharpfin-Downloads & m3u-Feeds
- https://github.com/jisotalo/reciva-radio-patching – IPdio-spezifische Patches (Grundlage für den Firmware-Pfad)
- https://github.com/philsmd/sharpfin – Sharpfin-Quellen (alter C++-Patchserver)
- https://github.com/felixalacampagne/recivaportal – Protokoll-Notizen, `sread`
- http://www.g3gg0.de/wordpress/reversing/reciva-encryption-on-reciva-barracuda/ – Reciva-Verschlüsselung
- https://web.archive.org/web/20250107210502/https://iradioforum.net/forum/index.php?topic=2968.0 – dliw: „Some findings“ (Original-Forum ist jetzt Gambling-Spam, daher Archiv-Version)
- https://leo.pfweb.eu/dl/JMCi1 – dliw-Tools (`sread`, `reciva_decrypt.py`)
- https://www.radio-browser.info/ – RadioBrowser-API
- https://www.home-assistant.io/integrations/radio_browser/ – HA-Integration
- https://music-assistant.io/ – Music Assistant (Metadaten & Streamserver)

---

## 15. Buy me a coffee

Wenn dir dieses Projekt geholfen hat und du die Arbeit unterstützen möchtest:

[![Sponsor this project](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://buymeacoffee.com/hanshauberger)

Oder direkt: https://buymeacoffee.com/hanshauberger

---

*Haftungsausschluss: Dieses Projekt nutzt eigene/backupsiche Kopien der
Patchserver-Komponenten und dient ausschließlich dem Weiterbetrieb bereits
im Besitz befindlicher Geräte. Keine Firmware-Binaries oder geheimen
 Schlüssel liegen diesem Repository bei.*
