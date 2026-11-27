# AGENTS.md – Reciva Patchserver / Sharpfin Radio: Rebuild-Playbook

Zweck: Ein anderer Agent soll damit den lokalen Patchserver + DNS-Proxy für ein
DNT IPdio (Reciva) Radio **von Grund auf nachbauen und verifizieren** können.
Dies ist die kompakte Arbeitsanleitung; `README.md` ist die Hintergrunddoku mit
vollständigen Skript-Listings.

---

## 0. Mission

Reciva ist abgeschaltet. Das Radio braucht weiterhin:

1. **DNS** für `*.reciva.com` / `*.7803986842.com` → lokaler Patchserver,
   alles andere → normales Internet (externe HTTP-Streams!).
2. **Portal** auf Port 80: Session (DES-Challenge/Response), `stations.xml`,
   `dynamic_menu`, NTP auf UDP 123.
3. **Install-Dateien** auf Port 8080: IPdio-Firmware-Patch, Sharpfin EP2,
   Media-Server, kleine m3u-Playlists.
4. **Senderdaten**: 48 Länder + 64 Genres aus RadioBrowser, dynamisch generiert,
   30 Details pro Paginierungsseite.

Zielzustand (akzeptiert am 23.11.2026, erweitert am 24.11.2026, DNT IPdio,
`v257-a-865-a-162-c-002`): Radio zeigt unter `Sender → Länder` und
`Sender → Musikrichtung` volle Listen, Scroll lädt nach, Wrap-around normal,
kein Reboot, ~4,6 MB freier RAM. Preset 99 zusätzlich per HA-Template-Player
mit RadioBrowser-/Music-Assistant-Titel befüllbar (siehe 7b).

Referenz-Host: **UGREEN NASync DXP4800 Plus** mit Docker/macvlan. Dort laufen
Patchserver, DNS-Proxy, Caddy-Relay, Home Assistant, Music Assistant, Jellyfin
und Portainer. Andere Linux-Docker-Hosts sind möglich, wenn macvlan nutzbar ist.

---

## 0b. Neues Radio – was zwingend ersetzt werden muss

Der Ablauf ist reproduzierbar, aber **nicht geräteunabhängig**. Nur der
DNT IPdio mit `v257-a-865-a-162-c-002` ist hier live verifiziert. Vor einem
zweiten Radio mindestens Folgendes prüfen:

| Element | Projekt | Bei neuem Radio |
|---|---|---|
| DES-Key | `<DES_KEY>` | **immer neu** mit dliw's `sread` auslesen; nie aus alter Config kopieren |
| Seriennummer | `<SERIAL>` | neu auslesen (`sernum`), in `dynamic_menu` und `.env` übernehmen |
| FTP/Telnet | `<PASSWORT>` | gerätebezogen, nicht aus der Doku übernehmen |
| IPs | `192.168.0.240/.242/.39/.50/.68` | Beispielwerte; `.env`, Docker-Netze und alle `curl`-Kommandos anpassen |
| Firmware-Patch | `sharpfin-base_0.3_IPdio.patch` | nur für die IPdio-Firmware. Anderes Modell → Patchdatei/Offset neu prüfen |
| Firmware-Version | `v257-a-865-a-162-c-002` | abweichende Version → „Upgrade Firmware" nicht blind ausführen |
| Sharpfin EP2 | Addon via `:8080` | gleicher Weg, aber nach dem Reboot erreichbar prüfen |
| HA/Preset 99 | `media_player.ipdio_preset99` | optional, nicht Voraussetzung für Patchserver + Menüs |
| Caddy-Relay | `192.168.0.68:8082` | nur nötig, falls HTTPS-Streams eingesetzt werden; LAN-only |

**Reihenfolge für ein neues Radio:** erst Inputs aus Abschnitt 3 einsammeln,
dann Server/DNS passiv testen, erst danach Radio-Schritte mit Freigabe. Wenn
ein Schritt nicht passt: anhalten und User fragen, statt zu raten.

**Historie des verifizierten IPdio (vom User berichtet, nicht verallgemeinern):**

1. Zuerst wurde ein **Sharpfin-Patch** aufgespielt, der **Telnet und den
   Webserver aktivierte**.
2. Danach kam ein **Update**.
3. Danach wurde ein **MediaPlayer** (UPnP-Fallback, `media-server-1.0`) addiert.
4. Um dafür Flash freizugeben, wurde der **ungenutzte japanische Font**
   `reciva_font_japanese.o` entfernt. **Das war keine Entfernung der Sprache
   „Japanisch" als UI-Funktion** – die Anzeigesprachen waren bereits de/en.
5. Erst danach traten der Webserver-Hang bei vollem Flash und die leeren
   CGI-Seiten auf (siehe 4.6 / README 7.3.1).

Diese Reihenfolge ist gerätebezogen. Bei einem neuen Radio **nicht** blind
nachmachen: erst echten Treiber (`rt73` vs. `zd1211*`), Sprachstand und `df -k /`
prüfen.

---

## 1. Harte Regeln – nicht verhandelbar

**Darfst du:**
- Server-/Container-Arbeiten nach Freigabe deployen.
- Passive HTTP-Gegenproben am Patchserver jederzeit machen.
- Backups anlegen und bei Bedarf rollbacken.

**Darfst du NICHT ohne ausdrückliche Freigabe:**
- Am Radio experimentieren, IR senden, `ir.log` lesen, Sniffing machen,
  Radio-Testansichten öffnen oder das Radio rebooten.
- Ins Radio `preset*.xml` direkt schreiben. **Nur die Sharpfin-UI ist Schreiber**
  (Store/Edit/Delete-CGIs). IR-Simulation ist kein Fix, sondern nur für
  explizit freigegebene Tests erlaubt.
- `menu_200014.xml` („Mein Podcast") verändern – bleibt Original-Platzhalter.
- Geheimnisse committen: `<DES_KEY>`, `<SERIAL>`, `<PASSWORT>`, `<HA_TOKEN>`
  bleiben Platzhalter. Keine `secrets.md.gpg`, keine echten Tokens oder
  Live-Konfigurationen ins Repo. Die geprüften Upstream-Binaries liegen
  bewusst unter `deploy/` und sind in `deploy/THIRD_PARTY.md` dokumentiert.

**Weitere Fixregeln:**
- Radio-Neustarts immer über den **Power-Button** (Software-Reboot kann WiFi
  verlieren). Neue `stations.xml` wird erst nach Power-Reboot übernommen.
- Keine HTTPS-Streams in Listen – die Firmware kann nur `http://`.
- Playlists ≤300 kB, besser ≤50 Tracks. Vor FTP-`STOR` Datei auf dem Radio
  löschen (`STOR` schneidet nicht ab).
- Jellyfin-Ersteinrichtung bleibt User-Aufgabe (`http://<JELLYFIN-IP>:8096`).

---

## 2. Zielzustand / Akzeptanzkriterien

| Komponente | Soll |
|---|---|
| `reciva-patchserver` | `192.168.0.240`, Image `reciva-patchserver:latest`, Entrypoint `/entrypoint.sh`, `--restart unless-stopped`, kein Mount, kein Port-Mapping |
| `reciva-dnsproxy` | `192.168.0.242`, gleiches Image, Entrypoint `python3 -u /opt/dnsproxy.py` |
| Patchserver-Binary | `/opt/RecivaServer/server`, SHA256 `2d899b010d4f5544a62183fe401a34e7970b189a4ddaaf99d6808b63f31689d0` |
| Original-Binary | `/opt/RecivaServer/server.bak-noClamp`, SHA256 `94ae9c257cbcca04e7739e0cd216271a61c670bdd04673e7e2c1e465b2a23a41` |
| Stationen | 48 Länder / 2.807 Sender (IDs `100001–102807`) + 64 Genres / 4.378 Sender (IDs `2000001–2004378`) = 7.185, 121 Views |
| Pagination | `count=30` → 30/30/30/10 Details bei `start=0/30/60/90` |
| Radio-DNS | dauerhaft `192.168.0.242` |
| Preset 99 | `media_player.ipdio_preset99`, Name aus RadioBrowser/MA, max. 40 Zeichen |

Alle IPs sind Beispielwerte – vorher mit dem User abklären und `<...>`
Platzhalter ersetzen.

---

## 3. Inputs einsammeln (bevor irgendwas gebaut wird)

- [ ] Radio-Modell + Firmware-Version erfasst; Abweichung von
      „DNT IPdio / `v257-a-865-a-162-c-002`“ geklärt (siehe 0b).
- [ ] LAN-Interface des Docker-Hosts (`<NIC>`), freie IPs, Gateway/Upstream-DNS.
- [ ] Radio-IP, Seriennummer `<SERIAL>`, FTP/Telnet-Passwort `<PASSWORT>`.
- [ ] **DES-Key `<DES_KEY>`** – gerätebezogen, nicht aus Doku übernehmen!
  Ablauf und Ausgabe von dliw's `sread` stehen in **Abschnitt 3b**:
  `killall sernum; /usr/bin/sernum --daemon; /tmp/sread -c 0000000000000000`
  (Null-Challenge → `462528ce4d91403f`). Firmware nutzt **DES** (IV
  `bde73266b946f3ab`), nicht AES.
- [ ] Patchserver-Artefakte liegen unter `deploy/RecivaServer/` und `deploy/files/`
      (Provenienz/Hashes: `deploy/THIRD_PARTY.md`).
- [ ] Freigaben einholen: Server-Deployment, Radio-Tests, große Importe.

### 3b. DES-Key mit `sread` auslesen (generell, gerätebezogen)

Der Key ist **pro Radio verschieden** und geheim. Er darf nie aus einer
anderen Konfiguration kopiert oder ins Repo geschrieben werden.

**Voraussetzungen**

- Shell-Zugang auf dem Radio (Telnet, bei Sharpfin `admin` / `<PASSWORT>`).
- `sread` ist eine **ARM-Binärdatei** (dliw, siehe Credits/THIRD_PARTY.md) und
  muss auf das Radio kopiert werden, z. B. nach `/tmp/sread`.
- Der `sernum`-Daemon muss laufen; er antwortet auf die lokalen Anfragen von
  `sread`.

**Ablauf auf dem Radio**

```sh
killall sernum
/usr/bin/sernum --daemon
/tmp/sread -c 0000000000000000
```

**Ausgabe interpretieren**

`sread [-v] [-c challenge] [-h]` akzeptiert eine hexadezimale Challenge von
maximal 8 Byte. Bei der Null-Challenge `0000000000000000` gibt es typischerweise:

```text
challenge response: 462528ce4d91403f   # Erwartungswert der Null-Challenge
key: <8 Byte hex>                      # <DES_KEY> – der gesuchte Wert
MAC key: <hex>                         # für dieses Setup nicht benötigt
```

- Die **Challenge Response** dient nur der Plausibilitätsprüfung. Weicht sie
  ab, nicht weiterfahren, sondern den Ablauf/das Gerät prüfen.
- Der Wert hinter `key:` ist der **8-Byte-DES-Key** (`<DES_KEY>`).
- Die Firmware nutzt **DES-CBC** mit IV `bde73266b946f3ab`, **nicht AES**.
  Die AES-Teile in `reciva_decrypt.py` betreffen andere Firmwares.
- Optional kann `reciva_decrypt.py` (gleiche Quelle) zum Nachvollziehen von
  Challenge/Session-Daten verwendet werden; die Konstanten `DES_iv` und die
  Helfer für Session Request/Response sind dort vorbereitet.

**Wohin der Key**

- In die Patchserver-Konfiguration: `configure_gui.sh`, Feld „EKey"
  (Xvfb-Koordinate `200,292`) und `.env` als `DES_KEY`.
- Nie committen: `<DES_KEY>`, `<SERIAL>`, `<PASSWORT>`, `<HA_TOKEN>`.
- Prüfen: Nach dem Setzen darf am Radio nicht „Kein Internet" erscheinen;
  die Session muss zustande kommen. Andernfalls zuerst den Key erneut
  auslesen, bevor andere Ursachen gesucht werden.

---

## 4. Build-Schritte

### 4.0 Deployment-Paket (bevorzugt)

Im Repo liegt `deploy/` mit Compose, Dockerfile und Skripten. Das ist der
kürzeste Weg und berührt das Radio nicht:

```sh
cd deploy
cp .env.example .env
# Pflichtfelder ausfüllen: PARENT_IFACE, IPs, RADIO_IP, DES_KEY, SERIAL
./scripts/install.sh
./scripts/verify.sh
```

`install.sh` nutzt die mitgelieferten `RecivaServer/`- und `files/`-Artefakte,
prüft die Patch-MD5, patched `RecivaServer/server` mit dem verifizierten
47-Byte-Snippet (Backup `.bak-noClamp`), legt das macvlan-Netz an und startet
`docker compose up -d --build`. Danach nur passiv prüfen; Radio-Änderungen
weiterhin nur nach Freigabe. Details: `deploy/README.md`,
`deploy/THIRD_PARTY.md`.

### 4.1 macvlan-Netz

```sh
docker network create -d macvlan --subnet=192.168.0.0/24 \
  --gateway=192.168.0.1 -o parent=<NIC> -o macvlan_mode=bridge reciva-net
```

macvlan-Container sind vom Docker-Host selbst nicht erreichbar → Checks von
einem LAN-Gerät oder per `docker exec`.

### 4.2 Image bauen

Debian 12, Pakete: `libgtk2.0-0 fonts-dejavu-core xvfb x11-utils xdotool scrot
fluxbox python3-minimal ca-certificates libssl3 python3-pil tesseract-ocr
at-spi2-core libgail-common python3-pyatspi python3-gi dbus-x11`;
`libssl.so.3`/`libcrypto.so.3` auf `.so` symlinken.
Dateien: `RecivaServer/`, `entrypoint.sh`, `configure_gui.sh` (mit `<DES_KEY>`),
`dnsproxy.py`, `ntp_server.py`. `WORKDIR /opt/RecivaServer`,
`ENTRYPOINT ["/entrypoint.sh"]`, `EXPOSE 80 443 8080 53/udp 123/udp`.
Vollständiges Dockerfile und Skripte: siehe `README.md` Abschnitte 4 und 6.

`entrypoint.sh` startet: Xvfb `:99` → fluxbox → dbus → HTTP-Server 8080 →
`ntp_server.py` → `configure_gui.sh` → `sync_sharpfin_menu.py` → `exec ./server`.

`configure_gui.sh` (Xvfb-Koordinaten 1024×768): DNS-Feld (300,38),
„Provide patch" (18,157), Patch-Radio (50,184), Combo (400,187, alt+Down/Home/
Return), „Full server" (18,344), EKey (200,292) → `<DES_KEY>`,
„Start session" (286,455). Original-Skript ohne Key als `.bak-zerokey` sichern.

### 4.3 DNS-Proxy-Logik (`/opt/dnsproxy.py`)

UDP 53, bind `0.0.0.0`; `UPSTREAM=(<ROUTER-IP>,53)`, `LOCAL_A=<PATCHSERVER-IP>`.
Namen, die `.7803986842.com` oder `.reciva.com` sind/enden, bekommen einen
A-Record auf `LOCAL_A`; alles andere wird unverändert an Upstream weitergeleitet
(bei Timeout SERVFAIL). **Kein** lokaler DNS für alle Domains – sonst sterben
externe Streams.

### 4.4 Patchserver-Binary patchen (exakt reproduzierbar)

Ziel: `stations_only` darf nie mehr als 30 Details liefern. Original-Handler:
`cmp dword [rsp],0` … `movsxd rdx,[rsp+4]` … `cmp rax,rdx` (nur wenn `count`
positiv ist wird geschnitten). Ohne `count` kam die komplette 51-kB-Liste →
Radio hing bei „Lade Senderliste" und rebootete.

Patch: `count` (Stack-Variable `[rsp+4]`) hart auf `0x1e` setzen und über die
alte Logik springen. Datei-Offset `0x1E1836` (= vaddr `0x5E16E2`), 47 Bytes:

```python
import hashlib, sys
src, dst = sys.argv[1], sys.argv[2]
data = bytearray(open(src, "rb").read())
OFF = 0x1E1836
OLD = bytes.fromhex(
    "833c24007f294584e40f84de0000004c89efe8d3650100"
    "4889c7e84b79010021c048635424044839d00f8ebe000000")
NEW = bytes.fromhex("c74424041e000000eb25" + "90" * 37)
assert len(OLD) == len(NEW) == 47
assert data[OFF:OFF+len(OLD)] == OLD, "falsche Binary-Version – Stopp!"
data[OFF:OFF+len(OLD)] = NEW
assert hashlib.sha256(data).hexdigest() == (
    "2d899b010d4f5544a62183fe401a34e7970b189a4ddaaf99d6808b63f31689d0")
open(dst, "wb").write(data)
```

Vorher `cp server server.bak-noClamp` (Hash prüfen!). Ergebnis:
`mov dword [rsp+4],0x1e; jmp 0x5E1711; NOPs`. Danach Container neu starten,
PID1 muss wieder `./server` sein.

### 4.5 Container starten

```sh
docker run -d --name reciva-patchserver --network reciva-net \
  --ip 192.168.0.240 --restart unless-stopped reciva-patchserver:latest
docker run -d --name reciva-dnsproxy --network reciva-net \
  --ip 192.168.0.242 --restart unless-stopped \
  --entrypoint python3 reciva-patchserver:latest -u /opt/dnsproxy.py
```

IPdio-Patchdatei ablegen (Original sichern):
`docker cp deploy/files/sharpfin-base_0.3_IPdio.patch reciva-patchserver:/opt/RecivaServer/patches/base_0.3.patch`
MD5 der ausgelieferten Datei: `043934970007ed0e83ad62ecb8d54b02`.

### 4.6 Radio (nur mit Freigabe!)

1. Radio-IP statisch, Gateway `<ROUTER-IP>`, **DNS dauerhaft `.242`**.
2. Power-Cycle, dann `Configure → Upgrade Firmware → YES` (Patch lädt von `.240`).
3. Sharpfin **EP2 ist ein Addon**, nicht Firmware:
   UI → `Install → Install Addon` → `http://<PATCHSERVER-IP>:8080/sharpfin-ep2.install`.
   **Stolperstein zuerst prüfen:** `df -k /` auf dem Radio. Hier waren nur
   **396 KB frei**, der Webserver hing während der Installation. Nicht die
   japanische Sprache war das Problem, sondern voller Flash: `rt73`-Radio
   braucht keine `zd1211*-driver.o`, de/en war schon aktiv,
   `reciva_font_japanese.o` war ungenutzt. Nach dem Entfernen: 760 KB frei.
   Nur bei gleichem Treiber-/Sprachenstand nachmachen – Details README 7.3.1.
   Falls danach CGI-Seiten leer bleiben (HTTP 200/0 B): Header in
   `/opt/webserver/cgi-bin/` auf `Content-type: text/html` korrigieren.
4. Optional Media Server 1.0 (UPnP-Fallback): `.../media-server-1.0.install`.

---

## 5. Senderdaten erzeugen & deployen

### 5.1 RadioBrowser-Import (auch via Home Assistant)

Quelle: HA-Integration **Radio Browser** (`media-source://radio_browser`, hier
`192.168.0.50`) liefert Favoriten/Kontrolldaten; der Massenexport läuft über
die öffentliche API (HA-UI kann keine ~7.000 Sender abfragen):

```text
GET https://de1.api.radio-browser.info/json/stations/search
 ?countrycode=DE&codec=MP3&hidebroken=true&order=votes&reverse=true&limit=500
# Genres: tag=<tag> statt countrycode
```

Filter: nur `http://`, URLs deduplizieren, max. 100 pro Land/Genre, Titel
ASCII-sicher. Ausgabe: M3U → Reciva-View
`stations/views/view_<loc>_<genre>_<lang>.xml` mit
`<version>4029</version>`, `<streamtype>1</streamtype>`, `MP3`,
`<protocol>http</protocol>`; `stations.xml` bekommt `<count>loc,genre,N</count>`.

Genre-Mapping (Auszug): `40=rock`, `6=80s`, `7=90s`, `28=jazz`,
`13=classic rock`, `46=varied`. 65 Reciva-Genres, 64 lieferten Sender
(`45=Unknown` hat keinen RadioBrowser-Tag). AD/LI/VA haben keine HTTP-MP3-Station.

**Geplant (nicht implementiert):** HA-Integration, die den Import direkt aus
Home Assistant auslöst. Nicht als vorhanden dokumentieren.

### 5.2 Import-Reihenfolge und Backups

Vollständige kopierbare Variante: **[`UPDATE.md`](UPDATE.md)** mit
`tools/update_stations.sh` und den Generatoren unter `tools/`.

1. `cd /opt/RecivaServer && tar czf stations.bak-$(date +%Y%m%d-%H%M%S).tar.gz stations`
2. Generatoren laufen lassen (M3U → Views + counts).
3. `tar czf reciva_import.tar.gz stations` → in Container kopieren →
   `tar xzf` in `/opt/RecivaServer`.
4. Passiv prüfen (siehe Abschnitt 6), dann **Power-Button-Reboot** am Radio.

Bestands-IDs: Länder `100001–102807`, Genres `2000001–2004378`. Aggregate-Views
`0_0_0`, `0_46_0`, `177_0_0`, `177_46_0` nicht überschreiben.

---

## 6. Verifikation (ohne Radio-Ja/Sagen)

```sh
# DNS
nslookup www.reciva.com <DNS-PROXY-IP>     # -> Patchserver-IP
nslookup example.com    <DNS-PROXY-IP>     # -> Internet

# Pagination (im Patchserver-Container, Klartext-GET)
for s in 0 30 60 90; do
  curl -s "http://127.0.0.1/portal-newformat/stations.xml?request_view=112_0_0&view_type=stations_only&start=$s&count=30" \
    | grep -c '<stream id='
done
# erwartet: 30 30 30 10   (auch bei genre 0_40_0)

# Zähler/Views
grep -o '<count>112,0,[^<]*' /opt/RecivaServer/stations/stations.xml   # 112,0,100
ls /opt/RecivaServer/stations/views | wc -l                            # 121
sha256sum /opt/RecivaServer/server                                     # 2d899b...
```

Radio-Tests (nur nach Freigabe, User navigiert, Agent überwacht Uptime/RAM):
`Sender → Länder → Europe → Germany` (erster `90s90s Hits`, letzter
`90s90s Techno`); `Sender → Musikrichtung → 80er` (100 Sender). Scroll bis
Ende, normaler Wrap-around, kein Reboot.

---

## 7. Dynamische Menüs / Presets (Sharpfin = Quelle der Wahrheit)

- Request: `POST /portal-newformat/dynamic_menu?serial=<SERIAL>` mit
  `dmenuid=<id>` im Body (**nicht** `id`/`menu_id`). Datei:
  `stations/dynamic/menu_<id>.xml`.
- IDs: `20009` Meine Sender, `200011` Meine Streams, `200014` Platzhalter
  (unantasten), `200059` DAR.FM, `HISTORY` lokal.
- Für `20009`/`200011` `scope="nocache"` in `stations.xml` und
  `/mnt/config/SLR_TopLevelMenuCache.xml`.
- Sync-Daemon liest alle 5 s den Preset-Manager
  (`http://<RADIO-IP>/cgi-bin/radio_Presets_Manage.cgi?start=1&end=20&action=program`)
  und schreibt die Menüs. Log `/tmp/sync_sharpfin.log`.
- Die drei Preset-CGIs (`radio_Presets_Store.cgi`, `Presets_edit.cgi`,
  `control_Presets.cgi`) müssen volle XML schreiben: eigene Station-ID
  `100+place`, Stream-ID `900+place`, `<version>`, `<protocol>`, `<metadata>`,
  `<locations>`, XML-Escaping. Original schrieb `<station id='3508'>` → Radio
  spielte „Sandisc". `preset0.xml` gehört dem Radio (Resume-Slot).
- station-ID-Kollisionen mit der Hauptdb (`view_0_0_0.xml`) vermeiden.

---

## 7b. HA-Template-Media-Player → Preset 99 (RadioBrowser/MA-Titel)

Ziel: Sender aus Home Assistant/RadioBrowser oder Music Assistant in den
Sharpfin-Preset 99 „pushen“. Auch hier ist **allein die Sharpfin-UI** der
Schreiber; niemals `preset*.xml` direkt anfassen.

**Harte Regeln**

- Nur `Presets_edit.cgi?...&place=99&action=program` speichert. Ein Aufruf ohne
  `name`/`url` erzeugt ein **leeres** Preset und ist kein Lese-Endpoint.
- `Presets_play.cgi?i=99` startet echtes Audio → nur nach ausdrücklicher
  Freigabe. Der Template-Player ist `optimistic`; HA `playing` beweist **keine**
  Wiedergabe.
- Kein `media_stop` im Template-Player (`supported_features: 512`). Stopp am
  Radio oder in der Sharpfin-UI.

**Entity-/Endpoint-Map**

```text
media_player.ipdio_preset99    Template-Player, unique_id ipdio_preset99
rest_command.ipdio_preset99_store → /cgi-bin/Presets_edit.cgi?name=…&url=…&place=99&action=program
rest_command.ipdio_preset99_play  → /cgi-bin/Presets_play.cgi?i=99
input_text.ipdio_rb_uuid          RadioBrowser-UUID aus media-source://radio_browser/<UUID>
input_text.ipdio_rb_stream_url    Original-URL aus builtin://radio/<URL>
sensor.ipdio_radiobrowser_url     /json/stations/byuuid/<UUID> → url_resolved/url
sensor.ipdio_radiobrowser_name    /json/stations/byuuid/<UUID> → name
sensor.ipdio_radiobrowser_name_by_url  /json/stations/byurl?url=<URL> → name
```

**YAML-Merge (wichtig)**

Auszüge in die **bereits vorhandenen** Top-Level-Blöcke `template:`,
`rest_command:`, `input_text:` und `rest:` der `configuration.yaml` einfügen.
Keine doppelten Top-Level-Keys. Keinen neuen `script:`-Block anlegen – es gibt
bereits `script: !include scripts.yaml`.

**Ablauf in `play_media`**

1. RadioBrowser-URI: UUID in `input_text.ipdio_rb_uuid` schreiben, dann
   `homeassistant.update_entity` für URL+Name-Sensor.
2. Andere Quellen (bes. MA): `media_content_id` des MA-Entities
   `media_player.ipdio_preset_99` prüfen; bei `builtin://radio/<URL>` die URL in
   `input_text.ipdio_rb_stream_url` schreiben, ByURL-Sensor aktualisieren, kurz
   warten.
3. Name in dieser Reihenfolge: RadioBrowser-Name → `extra.metadata.title` →
   `extra.title` → ByURL-Sensor → Host aus der URL.
4. `bad`-Liste verwirft `''`, `none`, `unknown`, `unavailable`, `no name`,
   `no_name`, `n/a`. Ergebnis auf **40 Zeichen** kürzen (Sharpfin-Feldbreite)
   und Zeilenumbrüche entfernen.
5. Stream-URL vor dem Store durch den Caddy-Relay leiten:
   `https://X` → `http://192.168.0.68:8082/https/X`,
   `http://X` → `http://192.168.0.68:8082/http/X`.
   Pfadlose URLs brauchen ein trailing `/`.
6. Store, `delay: "00:00:01"`, dann Play (Auto-Play nur nach Freigabe).

**Fallstricke**

- Der Relay auf Port `8082` bleibt **LAN-only** und wird nie veröffentlicht.
- ByURL-Endpoint ist `/json/stations/byurl?url=<URL>`, **nicht** `search?url=…`.
- Entity-ID lautet `sensor.ipdio_radiobrowser_name_by_url` (vom Namen
  abgeleitet); `sensor.ipdio_radiobrowser_byurl_name` ist nur die `unique_id`.
- `192.168.0.50:8097` ist der MA-Streamserver; `/info` liefert nur eine
  `server_id` und keinen Sendernamen. Titel kommt aus MA-Metadaten oder
  RadioBrowser.
- MA-Player muss einmalig unter *Settings → Player Providers → Home Assistant
  Media Players* importiert werden.

**Verifikation**

```sh
# HA-Validierung (Developer Tools oder CLI)
homeassistant.check_config
homeassistant.reload_all

# Nur lesend prüfen – NIEMALS Presets_edit.cgi ohne name/url aufrufen
curl -s 'http://192.168.0.39/cgi-bin/radio_Presets_Manage.cgi?start=99&end=99&action=program'
```

Live-verifizierte Titel: `Epic Lounge - IBIZA CHILLOUT LOUNGE` (UUID),
`Lane 8 Summer 2016 Mixtape` (MA-Metadaten),
`0R - CLASSICAL HOTEL LOUNGE - CLASSICAL` (MA `no name` via ByURL). Harmlos:
doppelte REST-`unique_id`-Warnungen im HA-Log und der fehlende `media_stop`.

---

## 8. Fehler → Aktion (Kurzform)

| Symptom | Aktion |
|---|---|
| „Kein Internet" | `<DES_KEY>` prüfen/neu auslesen, `configure_gui.sh` korrigieren |
| „Lade Senderliste" + Reboot | Binary-Patch fehlt → Abschnitt 4.4, Hash prüfen |
| Nur „Varied" unter Musikrichtung | `stations.xml` gecacht → Power-Button-Reboot |
| Senderliste leer | Radio-DNS ist nicht `.242` |
| Stream spielt nicht | HTTPS-URL → Caddy-Relay `http://192.168.0.68:8082/https/…` (oder `/http/…`) |
| Preset 99 zeigt `no name` | `input_text.ipdio_rb_stream_url` + ByURL-Sensor prüfen; Entity-ID `…name_by_url`, Endpoint `/json/stations/byurl?url=…` |
| HA zeigt `playing`, Radio ist still | `optimistic`! Store/Play-CGI und echte Audioausgabe prüfen |
| Preset spielt falschen Sender | ID-Kollision/alte Minimal-XML → über Sharpfin-UI neu speichern |
| Radio-Crash-Loop | m3u zu groß → ≤50 Tracks, vor Upload löschen |
| Uhr falsch | NTP-Prozess/UDP 123 prüfen |

Rollback: `tar xzf stations.bak-<ZEITSTEMPEL>.tar.gz`, bzw. `server.bak-noClamp`
zurückkopieren; danach Power-Reboot.

---

## 9. Reihenfolge / Abhängigkeiten (Kurzcheckliste)

```
[ ] Neues Radio: Modell/Firmware/Key/Serial geprüft (siehe 0b)
[ ] Inputs + Freigaben
[ ] macvlan-Netz
[ ] Image (DES-Key, Skripte, IPdio-Patchdatei)
[ ] Binary-Patch (Hash!)
[ ] Patchserver + DNS-Proxy starten
[ ] DNS + Pagination passiv prüfen
[ ] Radio: Netz/Firmware/EP2 (Freigabe!)
[ ] RadioBrowser-Import mit Backup + Power-Reboot
[ ] Dynamische Menüs/Sharpfin-CGIs prüfen
[ ] HA-Template-Player + RadioBrowser/MA-Titel (Freigabe für Auto-Play!)
[ ] Radio-Endtest (Freigabe!, User navigiert)
```

Offen: vollständige HA-Integration für den Import (Roadmap, noch nicht gebaut).
Der Template-Media-Player für Preset 99 ist dagegen umgesetzt und verifiziert.
