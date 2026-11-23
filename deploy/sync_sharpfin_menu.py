#!/usr/bin/env python3
"""Generate Reciva dynamic menus from the Sharpfin EP2 preset manager.

Source of truth: http://<RADIO-IP>/cgi-bin/radio_Presets_Manage.cgi
The radio fetches the generated XML via /portal-newformat/dynamic_menu
(dmenuid=20009 / 200011). Run as a small polling daemon on the patchserver.

The firmware keeps station data in RAM keyed by station ID and does not
refresh an already known ID just because name/url changed. Therefore:
  * <version> is bumped whenever the content really changes
  * station IDs are derived from (slot, name, url), so changed content gets
    a new ID while unchanged content keeps its ID.
"""
import hashlib
import html
import json
import os
import re
import time
import urllib.request

RADIO_IP = os.environ.get("RADIO_IP", "192.168.0.39").strip()
if not RADIO_IP or RADIO_IP.startswith("<"):
    raise SystemExit("sync_sharpfin_menu: RADIO_IP ist nicht gesetzt")

SOURCE = ("http://%s/cgi-bin/radio_Presets_Manage.cgi"
          "?start=1&end=20&action=program" % RADIO_IP)
BASE = "/opt/RecivaServer/stations/dynamic"
LOG = "/tmp/sync_sharpfin.log"
STATE = os.path.join(BASE, ".sync_state.json")

NS = "http://www.reciva.com/xml-schemas/reciva"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
HDR = ('<?xml version="1.0" encoding="utf-8"?>\n'
       '<reciva xmlns="%s" xmlns:xsi="%s" '
       'xsi:schemaLocation="%s http://www.reciva.com/xml-schemas/reciva3.xsd">\n'
       % (NS, XSI, NS))

ROW = re.compile(r'<tr id="(\d+)"[^>]*>(.*?)</tr>', re.S)
NAME = re.compile(r'<font color="#3333cc">(.*?)</font>', re.S)
URL = re.compile(r'<td>(https?://[^<]+)</td>')

# Main station database uses IDs 101..1949. Custom menus must stay far away.
# Non-overlapping ranges for the two dynamic menus:
#   My Streams   5,000,000 .. 5,099,999
#   My Stations  5,100,000 .. 5,799,999
STREAM_BASE, STREAM_SPAN = 5000000, 100000
STATION_BASE, STATION_SPAN = 5100000, 700000

VERSION_BASE = 4000


def log(msg):
    with open(LOG, "a") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def fetch():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "reciva-menu-sync"})
    body = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "replace")
    items = []
    for m in ROW.finditer(body):
        n, row = m.group(1), m.group(2)
        name, url = NAME.search(row), URL.search(row)
        if name and url:
            items.append((int(n), html.unescape(name.group(1)).strip(),
                          html.unescape(url.group(1)).strip()))
    return sorted(items)


def esc(s):
    return html.escape(s, quote=False)


def atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def load_state():
    try:
        with open(STATE) as f:
            d = json.load(f)
        return int(d.get("generation", 0)), str(d.get("fingerprint", ""))
    except Exception:
        return 0, ""


def save_state(gen, fingerprint):
    atomic(STATE, json.dumps({"generation": gen, "fingerprint": fingerprint}) + "\n")


def fingerprint(items):
    return hashlib.sha256(repr(items).encode("utf-8")).hexdigest()


def dynamic_id(base, span, n, name, url):
    """Stable for unchanged content, different as soon as name/url changes."""
    key = ("%d\0%s\0%s" % (n, name, url)).encode("utf-8")
    return base + int(hashlib.sha1(key).hexdigest()[:8], 16) % span


def menu_stations(items, version):
    s = HDR + '  <custommenu id="20009" position="PARENT">\n'
    s += "    <display>My Stations</display>\n"
    for n, name, url in items:
        sid = dynamic_id(STATION_BASE, STATION_SPAN, n, name, url)
        s += ('    <station id="%d" custommenuid="20009">%s</station>\n'
              % (sid, esc(name)))
    s += "  </custommenu>\n  <station-list>\n"
    for n, name, url in items:
        sid = dynamic_id(STATION_BASE, STATION_SPAN, n, name, url)
        s += ('    <station id="%d" custommenuid="20009" restart-on-match="false">\n'
              '      <version>%d</version>\n'
              '      <requireswversion>Any</requireswversion>\n'
              '      <streamtype>1</streamtype>\n'
              '      <suitableForPreset>1</suitableForPreset>\n'
              '      <data>\n'
              '        <stream>\n'
              '          <title>%s</title>\n'
              '          <url>%s</url>\n'
              '          <type>0</type>\n'
              '        </stream>\n'
              '      </data>\n'
              '    </station>\n') % (sid, version, esc(name), esc(url))
    return s + "  </station-list>\n</reciva>\n"


def menu_streams(items, version):
    streams = [(n, name, url) for n, name, url in items if ".m3u" in url.lower()]
    if not streams:
        streams = items[:2]
    s = HDR + '  <custommenu id="200011" position="PARENT">\n'
    s += "    <display>My Streams</display>\n"
    for n, name, url in streams:
        sid = dynamic_id(STREAM_BASE, STREAM_SPAN, n, name, url)
        s += ('    <station id="%d" custommenuid="200011">%s</station>\n'
              % (sid, esc(name)))
    s += "  </custommenu>\n  <station-list>\n"
    for n, name, url in streams:
        sid = dynamic_id(STREAM_BASE, STREAM_SPAN, n, name, url)
        s += ('    <station id="%d" custommenuid="200011" restart-on-match="false">\n'
              '      <version>%d</version>\n'
              '      <requireswversion>Any</requireswversion>\n'
              '      <streamtype>1</streamtype>\n'
              '      <suitableForPreset>1</suitableForPreset>\n'
              '      <data>\n'
              '        <stream>\n'
              '          <title>%s</title>\n'
              '          <url>%s</url>\n'
              '          <type>0</type>\n'
              '        </stream>\n'
              '      </data>\n'
              '    </station>\n') % (sid, version, esc(name), esc(url))
    return s + "  </station-list>\n</reciva>\n"


def main():
    log("=== sync daemon start === (radio %s)" % RADIO_IP)
    gen, old_fp = load_state()
    log("state loaded: generation=%d" % gen)
    last_fp = None
    while True:
        try:
            items = fetch()
            if items:
                fp = fingerprint(items)
                if fp != last_fp:
                    if fp != old_fp:
                        new_gen = gen + 1
                        version = VERSION_BASE + new_gen
                        atomic(os.path.join(BASE, "menu_20009.xml"),
                               menu_stations(items, version))
                        atomic(os.path.join(BASE, "menu_200011.xml"),
                               menu_streams(items, version))
                        save_state(new_gen, fp)
                        gen, old_fp = new_gen, fp
                        first = dynamic_id(STATION_BASE, STATION_SPAN,
                                           items[0][0], items[0][1], items[0][2])
                        log("updated %d presets (gen=%d, version=%d, first_id=%d): %s"
                            % (len(items), gen, version, first,
                               ", ".join(n for _, n, _ in items)))
                    else:
                        version = VERSION_BASE + gen
                        atomic(os.path.join(BASE, "menu_20009.xml"),
                               menu_stations(items, version))
                        atomic(os.path.join(BASE, "menu_200011.xml"),
                               menu_streams(items, version))
                        log("refreshed menu files (gen=%d, unchanged)" % gen)
                    last_fp = fp
        except Exception as exc:
            log("error: %s" % exc)
        time.sleep(5)


if __name__ == "__main__":
    main()
