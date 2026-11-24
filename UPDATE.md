# Manuelles Update der Senderlisten

Diese Anleitung beschreibt den kompletten Weg von der RadioBrowser-API bis zum
lokalen Patchserver. Sie ist **selbstständig ausführbar** – es müssen keine
Skripte mehr aus einer anderen Doku zusammengesucht werden.

> **Umfang vorher bestätigen:** Länder Europa + England/UK + USA + Australien
> (48 Länder) und 64 Genres, maximal 100 Sender pro Land/Genre. Aktuell sind das
> 2.807 + 4.378 = **7.185 Sender in 121 Views**. Ein Großimport verändert den
> Menübestand deutlich – vorher mit dem User abklären.

## Voraussetzungen

- Patchserver-Container läuft: `reciva-patchserver` auf `192.168.0.240`.
- Auf dem Docker-Host: `python3`, `curl`, `docker`, `tar`.
- RadioBrowser-API ist erreichbar (`de1.api.radio-browser.info`).
- Kein Radio-Test nötig, bis am Ende der **Power-Button** gedrückt wird.

---

## 1. Empfohlen: ein Befehl

Im Repo-Root:

```sh
# Nur bauen, noch nichts deployen:
./tools/update_stations.sh

# Bauen, Backup im Container machen und deployen:
./tools/update_stations.sh --apply
```

Der Wrapper macht der Reihe nach:

1. aktuellen `/opt/RecivaServer/stations` aus dem Container holen,
2. `rb_countries.json` von RadioBrowser laden (mit `--skip-fetch` überspringbar),
3. Länder: 100 HTTP-MP3-Sender pro Land → M3U → `view_<loc>_0_0.xml`,
4. Genres: 100 HTTP-MP3-Sender pro Genre → M3U → `view_0_<genre>_0.xml`,
5. bestehenden Baum behalten und nur Views + `stations.xml` überschreiben,
6. `stations.bak-<ZEITSTEMPEL>.tar.gz` im Container anlegen und entpacken.

Danach **einmal am Radio den Power-Button drücken**. Ohne Reboot zeigt das Radio
noch die gecachte alte `stations.xml` (z. B. nur „Varied“ unter Musikrichtung).

---

## 2. Schritt für Schritt (ohne Wrapper)

Falls die einzelnen Schritte sichtbar sein sollen:

```sh
cd /path/to/RECIVA-Sharpfin-Radio
export RB_WORK="$PWD/tools/work"
mkdir -p "$RB_WORK"

# Aktuellen Baum und stations.xml holen
rm -rf "$RB_WORK/stations_current/stations"
mkdir -p "$RB_WORK/stations_current"
docker cp reciva-patchserver:/opt/RecivaServer/stations \
  "$RB_WORK/stations_current/stations"
export STATIONS_XML="$RB_WORK/stations_current/stations/stations.xml"

# Länderliste
curl -fsSL https://de1.api.radio-browser.info/json/countries \
  -o "$RB_WORK/rb_countries.json"

# Länder-Import (100 pro Land)
python3 tools/build_radiobrowser_100.py
python3 tools/build_reciva_views_100.py

# Genre-Import (100 pro Genre), counts aus dem Länder-Ergebnis weiterführen
python3 tools/build_radiobrowser_genres.py
STATIONS_XML="$RB_WORK/reciva_stations_pkg_100/stations/stations.xml" \
  python3 tools/build_reciva_genres.py

# Finalen Baum zusammenstellen: alter Baum + neue Länder-/Genre-Views
FINAL="$RB_WORK/stations_new"
rm -rf "$FINAL"
mkdir -p "$FINAL"
cp -a "$RB_WORK/stations_current/stations/." "$FINAL/"
mkdir -p "$FINAL/views"
cp -a "$RB_WORK/reciva_stations_pkg_100/stations/views/." "$FINAL/views/"
cp -a "$RB_WORK/reciva_genres_pkg/stations/views/." "$FINAL/views/"
cp -f "$RB_WORK/reciva_genres_pkg/stations/stations.xml" "$FINAL/stations.xml"

# Prüfen und paketieren
find "$FINAL/views" -maxdepth 1 -name 'view_*_0_0.xml' | wc -l   # 48 Länder
find "$FINAL/views" -maxdepth 1 -name 'view_0_*_0.xml' | wc -l   # 64 Genres
tar czf "$RB_WORK/reciva_update.tar.gz" -C "$FINAL" .
```

Deploy mit Backup:

```sh
docker cp "$RB_WORK/reciva_update.tar.gz" \
  reciva-patchserver:/tmp/reciva_update.tar.gz
docker exec reciva-patchserver sh -c \
  'cd /opt/RecivaServer && \
   tar czf stations.bak-$(date +%Y%m%d-%H%M%S).tar.gz stations && \
   tar xzf /tmp/reciva_update.tar.gz -C stations'
```

Danach: **Power-Button am Radio**.

---

## 3. Verifikation (passiv, ohne Radio-Interaktion)

```sh
docker exec reciva-patchserver sh -c '
  grep -o "<count>112,0,[^<]*" /opt/RecivaServer/stations/stations.xml
  find /opt/RecivaServer/stations/views -maxdepth 1 -type f | wc -l
  sha256sum /opt/RecivaServer/server
'
# erwartet: 112,0,100 / 121 / 2d899b01...89d0

for s in 0 30 60 90; do
  curl -s "http://192.168.0.240/portal-newformat/stations.xml?request_view=112_0_0&view_type=stations_only&start=$s&count=30" \
    | grep -c '<stream id='
done
# erwartet: 30 30 30 10  (gleiche Prüfung für 0_40_0 = Rock)
```

Erst nach diesen Prüfungen den Radio-Test freigeben und selbst navigieren:
`Sender → Länder → Europe → Germany` und
`Sender → Musikrichtung → 80er`.

---

## 4. Rollback

```sh
docker exec reciva-patchserver sh -c \
  'cd /opt/RecivaServer && rm -rf stations && \
   tar xzf stations.bak-<ZEITSTEMPEL>.tar.gz'
```

Danach wieder **Power-Button** am Radio. Weitere Backups dieser Installation:
`server.bak-noClamp`, `stations.bak-before100-*`,
`stations.bak-beforeGenre-*`, `configure_gui.sh.bak-zerokey`.

---

## 5. Die Skripte im Detail

Alle Skripte liegen unter `tools/` und nutzen `RB_WORK` als Arbeitsverzeichnis
(Default: `tools/work`). `STATIONS_XML` kann einzeln überschrieben werden.

| Skript | Aufgabe |
|---|---|
| `build_radiobrowser.py` | Älterer 40-Sender-Export, alle Länder |
| `build_radiobrowser_25.py` | Älterer 25-Sender-Export (Erstimport) |
| `build_radiobrowser_eu.py` | EU-Variante ohne Australien |
| `build_radiobrowser_100.py` | **Final:** 100 HTTP-MP3-Sender je Land → `radiobrowser_out_100/` + Manifest |
| `build_radiobrowser_genres.py` | **Final:** 100 Sender je Reciva-Genre → `radiobrowser_out_genres/` + Manifest |
| `build_reciva_views.py` | Ältere 25er-Länder-Views |
| `build_reciva_views_100.py` | **Final:** Länder-Views + Länder-Counts in `stations.xml` |
| `build_reciva_genres.py` | **Final:** Genre-Views + Genre-Counts in `stations.xml` |
| `update_stations.sh` | Orchestriert den kompletten Ablauf inkl. Backup/Deploy |

Wichtige Konstanten in den Skripten:

- nur `http://`-URLs, `codec=MP3`, `hidebroken=true`, Sortierung nach Votes,
- Titel werden ASCII-sicher gemacht und gekürzt,
- Länder-IDs `100001–102807`, Genre-IDs `2000001–2004378`,
- Aggregat-Views `0_0_0`, `0_46_0`, `177_0_0`, `177_46_0` nicht überschreiben,
- `menu_200014.xml` bleibt der Original-Platzhalter.

---

## 6. Häufige Stolpersteine

| Symptom | Ursache / Lösung |
|---|---|
| Menü zeigt alten Stand | Kein Power-Button-Reboot nach dem Deploy |
| „Nur Varied“ unter Musikrichtung | `stations.xml` gecacht → Power-Button |
| Views-Anzahl passt nicht | Wrapper meldet `Länder-Views / Genre-Views / gesamt`; Minimum 48/64 prüfen |
| Sender spielt nicht | HTTPS-URL → über Caddy-Relay aus [README 10a](README.md#10a-caddy-https-streams-für-den-ipdio-http-relay) |
| Skript findet `stations.xml` nicht | `STATIONS_XML` setzen oder `update_stations.sh` ohne eigene Pfade nutzen |
| RadioBrowser liefert weniger Sender | Tag/land vorübergehend leer → `radiobrowser_errors_*.json` im Arbeitsverzeichnis prüfen |
