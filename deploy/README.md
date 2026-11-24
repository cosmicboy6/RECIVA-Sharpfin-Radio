# Deployment-Paket (Docker Compose)

Damit ist die Installation auf einem Docker-Host praktisch ein Befehl. Das
Paket baut dasselbe Image, das auch in `README.md` / `AGENTS.md` beschrieben
ist, und startet genau zwei Container im macvlan-Netz:

| Container | IP (Beispiel) | Aufgabe |
|---|---|---|
| `reciva-patchserver` | `192.168.0.240` | Portal, NTP, Install-Dateien, dynamische Menüs |
| `reciva-dnsproxy` | `192.168.0.242` | Reciva-Domains umleiten, Rest forwarden |

**Enthalten:** die Upstream-Artefakte `RecivaServer/server`,
`RecivaServer/server.bak-noClamp`, `files/sharpfin-base_0.3_IPdio.patch`,
`sharpfin-ep2.install` sowie die Media-Server-Installer. Provenienz, Hashes und
Lizenzhinweise stehen in [`THIRD_PARTY.md`](THIRD_PARTY.md).

**Nicht enthalten:** echte Geheimnisse. `.env.example` hat nur Platzhalter;
der DES-Key wird zur Laufzeit injiziert.

---

## Schnellstart

```sh
cd deploy
cp .env.example .env
# .env ausfüllen: PARENT_IFACE, IPs, DES_KEY, SERIAL, RADIO_IP ...

./scripts/install.sh
./scripts/verify.sh

# Optional mit eigenen Dateien:
# ./scripts/install.sh --server-dir /pfad/zu/RecivaServer \
#   --patch-file /pfad/zu/sharpfin-base_0.3_IPdio.patch
```

Danach am Radio: DNS dauerhaft auf `DNS_PROXY_IP` setzen und per
**Power-Button** neu starten. Die weiteren Radio-Schritte stehen in der
Haupt-README, Abschnitt 7.

---

## Was `install.sh` macht

1. `.env` prüft (Platzhalter werden abgelehnt).
2. `RecivaServer/` und die IPdio-Patchdatei an ihren Build-Platz kopieren.
3. Patchdatei per MD5 prüfen (`043934970007ed0e83ad62ecb8d54b02`).
4. `RecivaServer/server` mit dem verifizierten 30er-Clamp patchen
   (Backup `server.bak-noClamp` entsteht im Build-Ordner). Erkennt das Skript
   das bereits gepatchte Binary am SHA256, passiert nichts.
5. Das macvlan-Netz anlegen, falls es fehlt (`RECIVA_NET`, `SUBNET`,
   `GATEWAY`, `PARENT_IFACE` aus `.env`).
6. `docker compose up -d --build` ausführen.

Das Radio wird dabei **nicht** angefasst. Bestehende Container mit anderen
Namen bleiben unberührt.

---

## Wichtige `.env`-Werte

| Variable | Bedeutung |
|---|---|
| `PARENT_IFACE` | Physische NIC des Docker-Hosts, z. B. `eth0`, `bond0`, `bridge0` |
| `PATCHSERVER_IP` | IP des Portals (muss `LOCAL_A` im DNS-Proxy sein) |
| `DNS_PROXY_IP` | IP, die am Radio als DNS eingetragen wird |
| `UPSTREAM_DNS` | Router/Internet-DNS für alle nicht-Reciva-Domains |
| `RADIO_IP` | IP des Radios, für den Sharpfin-Preset-Sync |
| `DES_KEY` | Gerätebezogener 8-Byte-Key, zur Laufzeit injiziert – nicht ins Image |
| `SERIAL` | Seriennummer des Radios, nur als Platzhalter dokumentiert |

`PASSWORT` und `HA_TOKEN` sind für spätere Schritte reserviert und werden
aktuell nicht verwendet. Bitte trotzdem nie echte Werte committen; `.env`
ist gitignored.

---

## Dateien

```text
deploy/
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── configure_gui.sh
├── dnsproxy.py
├── ntp_server.py
├── sync_sharpfin_menu.py
├── patch_server.py
├── THIRD_PARTY.md               # Provenienz, Hashes, Lizenzhinweise
├── scripts/
│   ├── install.sh
│   └── verify.sh
├── files/                       # Upstream-Artefakte (Patch, EP2, Media Server)
└── RecivaServer/                # Upstream-Binary + server.bak-noClamp
```

---

## Prüfung und Rollback

`./scripts/verify.sh` prüft passiv:

- Patchserver-SHA256 (`2d899b01…89d0`)
- DNS: `www.reciva.com` → Patchserver, externe Domain → Upstream
- Pagination `30 30 30 10` für Länder- und Genre-Views
- Anzahl Views / Deutschland-Count als Hinweis (nicht hart fehlerhaft)

Bei Problemen:

```sh
docker logs reciva-patchserver
docker logs reciva-dnsproxy
docker compose down
# RecivaServer/server.bak-noClamp zurückkopieren und erneut installieren
```

Weitere Backups und Radio-Schritte: siehe `README.md` Abschnitte 7, 8 und 11.
