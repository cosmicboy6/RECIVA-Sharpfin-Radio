#!/usr/bin/env python3
"""Build Reciva genre views (view_0_<genre>_0.xml) from RadioBrowser tag set."""
import json, os, re, shutil, unicodedata
from xml.sax.saxutils import escape
WORK = os.environ.get("RB_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))

SRC = os.path.join(WORK, "radiobrowser_out_genres")
MANIFEST = os.path.join(WORK, "radiobrowser_manifest_genres.json")
STATIONS_XML = os.environ.get("STATIONS_XML", os.path.join(WORK, "stations_live_beforeGenre.xml"))
OUT = os.path.join(WORK, "reciva_genres_pkg")
SID_START = 2000000

REPLACE = {
    "Ä": "Ae", "ä": "ae", "Ö": "Oe", "ö": "oe", "Ü": "Ue", "ü": "ue",
    "ß": "ss", "Å": "A", "å": "a", "Æ": "AE", "æ": "ae", "Ø": "O",
    "ø": "o", "É": "E", "é": "e", "È": "E", "è": "e", "Ê": "E", "ê": "e",
    "Ó": "O", "ó": "o", "Ô": "O", "ô": "o", "Ç": "C", "ç": "c",
    "Ñ": "N", "ñ": "n", "Í": "I", "í": "i", "Ú": "U", "ú": "u",
    "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-",
}


def ascii_text(s):
    s = "".join(REPLACE.get(c, c) for c in s)
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    s = "".join(c if 32 <= ord(c) < 127 else " " for c in s)
    return re.sub(r"\s+", " ", s).strip()


def parse_m3u(path):
    out = []
    title = None
    for line in open(path, encoding="utf-8", errors="replace").read().splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            title = ascii_text(line[8:].strip())
        elif title and line.startswith("http://"):
            out.append((title, line))
            title = None
    return out


shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT + "/stations/views", exist_ok=True)
manifest = json.load(open(MANIFEST, encoding="utf-8"))
dirs = {}
for d in os.listdir(SRC):
    m = re.match(r"(\d+)_", d)
    if m:
        dirs[int(m.group(1))] = d
counts = []
total = 0
sid = SID_START

for item in manifest:
    gid = item["id"]
    d = dirs.get(gid)
    if not d:
        raise SystemExit("missing dir for genre " + str(gid))
    stations = parse_m3u(os.path.join(SRC, d, "genre.m3u"))
    if not stations:
        raise SystemExit("no stations in " + d)
    counts.append((gid, len(stations)))
    view_entries = []
    detail_entries = []
    for title, url in stations:
        sid += 1
        t = escape(title or "Unknown")
        u = escape(url)
        view_entries.append('      <station id="%d">%s</station>' % (sid, t))
        detail_entries.append("""    <station id="%d">
       <version>4029</version>
       <requireswversion>Any</requireswversion>
       <streamtype>1</streamtype>
       <genres>%d</genres>
       <locations>0</locations>
       <data>
         <stream id="%d">
           <title>%s</title>
           <url>%s</url>
           <codec>MP3</codec>
           <bitrate>128</bitrate>
           <protocol>http</protocol>
         </stream>
       </data>
     </station>""" % (sid, gid, sid, t, u))
    xml = """<?xml version="1.0" encoding="utf-8"?>
<reciva xmlns="http://www.reciva.com/xml-schemas/reciva" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.reciva.com/xml-schemas/reciva http://www.reciva.com/xml-schemas/reciva2.xsd">
  <radio-serial></radio-serial>
  <stamp></stamp>
  <view-list>
    <view version="0" location="0" genre="%d" language="0">
%s
    </view>
  </view-list>
  <station-list>
%s
  </station-list>
</reciva>
""" % (gid, "\n".join(view_entries), "\n".join(detail_entries))
    open("%s/stations/views/view_0_%d_0.xml" % (OUT, gid), "w", encoding="utf-8").write(xml)
    total += len(stations)

text = open(STATIONS_XML, encoding="utf-8").read()
block = re.search(r"  <station-counts>(.*?)</station-counts>", text, re.S)
if not block:
    raise SystemExit("no station-counts block")
start, end = block.start(), block.end()
cnt_lines = re.findall(r"<count>([^<]+)</count>", block.group(1))
existing = {}
for idx, line in enumerate(cnt_lines):
    parts = line.split(",")
    if len(parts) == 3 and parts[0] == "0" and parts[1] != "0":
        existing.setdefault(int(parts[1]), idx)

for gid, n in counts:
    newval = "0,%d,%d" % (gid, n)
    if gid in existing:
        cnt_lines[existing[gid]] = newval
    else:
        existing[gid] = len(cnt_lines)
        cnt_lines.append(newval)

block_text = "  <station-counts>\n" + "".join(
    "    <count>%s</count>\n" % c for c in cnt_lines) + "  </station-counts>"
text = text[:start] + block_text + text[end:]
open(OUT + "/stations/stations.xml", "w", encoding="utf-8").write(text)

print("genres", len(manifest), "stations", total, "last_id", sid)
print("views", len(os.listdir(OUT + "/stations/views")))
print("counts", len(re.findall(r"<count>", text)))
print("rock count", [c for c in re.findall(r"<count>([^<]+)</count>", text) if c.startswith("0,40,")])
print("varied count", [c for c in re.findall(r"<count>([^<]+)</count>", text) if c.startswith("0,46,")])
