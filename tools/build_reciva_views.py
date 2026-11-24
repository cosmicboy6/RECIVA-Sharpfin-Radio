#!/usr/bin/env python3
"""Build local Reciva station XML (country views) from the RadioBrowser m3u set."""
import json, os, re, shutil, unicodedata
from xml.sax.saxutils import escape
WORK = os.environ.get("RB_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))

SRC = os.path.join(WORK, "radiobrowser_out_25")
MANIFEST = os.path.join(WORK, "radiobrowser_manifest_25.json")
STATIONS_XML = os.environ.get("STATIONS_XML", os.path.join(WORK, "stations_clean.xml"))
OUT = os.path.join(WORK, "reciva_stations_pkg")

LOC = {
    "AL": 27, "AM": 35, "AT": 39, "AU": 38, "AZ": 900, "BA": 54,
    "BE": 48, "BG": 60, "BY": 47, "CH": 252, "CY": 25, "CZ": 86,
    "DE": 112, "DK": 87, "EE": 98, "ES": 233, "FI": 104, "FR": 105,
    "GB": 255, "GE": 111, "GR": 116, "HR": 84, "HU": 130, "IE": 136,
    "IS": 131, "IT": 138, "LT": 162, "LU": 163, "LV": 156, "MC": 182,
    "MD": 181, "ME": 538, "MK": 164, "MT": 171, "NL": 191, "NO": 201,
    "PL": 214, "PT": 215, "RO": 216, "RS": 230, "RU": 206, "SE": 251,
    "SI": 232, "SK": 231, "SM": 901, "TR": 253, "UA": 254, "US": 300,
}

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


def norm(s):
    return ascii_text(s).lower().replace(" ", "")


def parse_m3u(path):
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    out = []
    title = None
    for line in lines:
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
dirs = {norm(d): d for d in os.listdir(SRC)}
counts = []
total = 0
sid = 1000

for item in manifest:
    code = item["code"]
    loc = LOC[code]
    d = dirs.get(norm(item["country"]))
    if not d:
        raise SystemExit("missing directory for " + item["country"])
    stations = parse_m3u(os.path.join(SRC, d, d + ".m3u"))
    if not stations:
        raise SystemExit("no stations in " + d)
    counts.append((loc, len(stations)))
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
      <genres>0</genres>
      <locations>%d</locations>
      <data>
        <stream id="%d">
          <title>%s</title>
          <url>%s</url>
          <codec>MP3</codec>
          <bitrate>128</bitrate>
          <protocol>http</protocol>
        </stream>
      </data>
    </station>""" % (sid, loc, sid, t, u))
    xml = """<?xml version="1.0" encoding="utf-8"?>
<reciva xmlns="http://www.reciva.com/xml-schemas/reciva" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.reciva.com/xml-schemas/reciva http://www.reciva.com/xml-schemas/reciva2.xsd">
  <radio-serial></radio-serial>
  <stamp></stamp>
  <view-list>
    <view version="0" location="%d" genre="0" language="0">
%s
    </view>
  </view-list>
  <station-list>
%s
  </station-list>
</reciva>
""" % (loc, "\n".join(view_entries), "\n".join(detail_entries))
    open("%s/stations/views/view_%d_0_0.xml" % (OUT, loc), "w", encoding="utf-8").write(xml)
    total += len(stations)

# stations.xml: append custom locations and country counts
text = open(STATIONS_XML, encoding="utf-8").read()
text = text.lstrip("\ufeff\ufffd\x00")
text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
text = re.sub(
    r'(<display>Asia</display>.*?)(      </level>)',
    r'\1        <location id="900">Azerbaijan</location>\n\2',
    text, count=1, flags=re.S)
text = re.sub(
    r'(<display>Europe</display>.*?)(      </level>)',
    r'\1        <location id="901">San Marino</location>\n\2',
    text, count=1, flags=re.S)
old_counts = re.findall(r"<count>([^<]+)</count>", text)
all_counts = old_counts + ["%d,0,%d" % (loc, n) for loc, n in counts]
new_block = "  <station-counts>\n" + "".join(
    "    <count>%s</count>\n" % c for c in all_counts) + "  </station-counts>"
text = re.sub(r"  <station-counts>.*?</station-counts>", new_block, text,
              count=1, flags=re.S)
open(OUT + "/stations/stations.xml", "w", encoding="utf-8").write(text)

print("countries", len(manifest), "stations", total, "last_id", sid)
print("views", len(os.listdir(OUT + "/stations/views")))
print("counts", len(all_counts))
