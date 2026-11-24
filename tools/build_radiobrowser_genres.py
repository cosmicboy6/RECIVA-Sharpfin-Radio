import json, os, re, urllib.parse, urllib.request
WORK = os.environ.get("RB_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))

BASE = "https://de1.api.radio-browser.info/json/stations/search"
OUT = os.path.join(WORK, "radiobrowser_out_genres")
WANT = 100

# Reciva genre id -> RadioBrowser tag candidates (tried in order until 100).
TAGS = {
    58: ["60s", "1960s"], 5: ["70s", "1970s"], 6: ["80s", "1980s"],
    7: ["90s", "1990s"], 9: ["alternative"], 69: ["ambient"],
    52: ["bluegrass"], 10: ["blues"], 60: ["bollywood"],
    11: ["christian"], 12: ["christian contemporary", "contemporary christian"],
    15: ["college"], 62: ["comedy"], 17: ["country"], 19: ["discussion"],
    71: ["drum and bass", "drum & bass", "dnb"], 20: ["easy listening", "easy"],
    21: ["electronic", "electronica"], 57: ["adult"], 8: ["adult contemporary"],
    22: ["experimental"], 23: ["folk"], 24: ["gospel"], 25: ["greek"],
    26: ["hip hop", "hiphop"], 27: ["indie"], 54: ["indie rock"],
    65: ["indian"], 28: ["jazz"], 72: ["jungle"], 59: ["kids"],
    13: ["classic rock"], 14: ["classical"], 29: ["latin", "latin hits"],
    30: ["news"], 32: ["news"], 51: ["new age"], 31: ["news talk", "talk"],
    35: ["public radio", "public"], 33: ["oldies"], 34: ["pop"],
    36: ["punk"], 37: ["r&b", "rnb", "rhythm and blues"], 38: ["rap"],
    48: ["reggae"], 39: ["religious"], 40: ["rock"], 73: ["shortwave", "short wave"],
    41: ["soft rock"], 66: ["spanish"], 42: ["sports"], 43: ["talk"],
    18: ["dance"], 44: ["top 40", "top40"], 45: [],
    46: ["varied", "variety"], 49: ["world"], 67: ["african", "africa"],
    47: ["asian", "asia"], 56: ["european", "europe"], 68: ["caribbean"],
    55: ["mediterranean"], 50: ["middle east", "arabic"], 53: ["tropical"],
    16: ["contemporary"],
}

GENRES = {
    58: "60s", 5: "70s", 6: "80s", 7: "90s", 9: "Alternative", 69: "Ambient",
    52: "Bluegrass", 10: "Blues", 60: "Bollywood", 11: "Christian",
    12: "Christian Contemporary", 15: "College", 62: "Comedy", 17: "Country",
    19: "Discussion", 71: "Drum & Bass", 20: "Easy", 21: "Electronica",
    57: "Adult", 8: "Adult Contemporary", 22: "Experimental", 23: "Folk",
    24: "Gospel", 25: "Greek", 26: "Hip Hop", 27: "Indie", 54: "Indie Rock",
    65: "Indian", 28: "Jazz", 72: "Jungle", 59: "Kids", 13: "Classic Rock",
    14: "Classical", 29: "Latin Hits", 30: "News", 32: "News Updates",
    51: "New Age", 31: "News Talk", 35: "Public", 33: "Oldies", 34: "Pop",
    36: "Punk", 37: "R&B", 38: "Rap", 48: "Reggae", 39: "Religious",
    40: "Rock", 73: "Short Wave Radio", 41: "Soft Rock", 66: "Spanish",
    42: "Sports", 43: "Talk", 18: "Dance", 44: "Top 40", 45: "Unknown",
    46: "Varied", 49: "World", 67: "World Africa", 47: "World Asia",
    56: "World Europe", 68: "World Caribbean", 55: "World Mediterranean",
    50: "World Middle East", 53: "World Tropical", 16: "Contemporary",
}


def fetch(tag):
    q = urllib.parse.urlencode({
        "tag": tag, "codec": "MP3", "hidebroken": "true",
        "order": "votes", "reverse": "true", "limit": "500",
    })
    req = urllib.request.Request(BASE + "?" + q, headers={"User-Agent": "reciva-import/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def safe(s):
    s = re.sub(r'[\x00-\x1f/\\:*?"<>|]', '', s).strip()
    return re.sub(r'\s+', ' ', s)[:40].rstrip(' .')


def title(s):
    return re.sub(r'\s+', ' ', re.sub(r'[\x00-\x1f\r\n]', ' ', s or '')).strip()[:48]


os.makedirs(OUT, exist_ok=True)
manifest, errors = [], []
for i, (gid, tags) in enumerate(sorted(TAGS.items()), 1):
    name = GENRES[gid]
    picked, seen, used = [], set(), []
    for tag in tags:
        try:
            rows = fetch(tag)
        except Exception as e:
            errors.append((gid, name, tag, repr(e)))
            continue
        used.append(tag)
        for st in rows:
            url = (st.get("url_resolved") or st.get("url") or "").strip()
            if not url.lower().startswith("http://") or url in seen:
                continue
            seen.add(url)
            picked.append((title(st.get("name") or name), url))
            if len(picked) == WANT:
                break
        if len(picked) == WANT:
            break
    if not picked:
        errors.append((gid, name, "all tags", "none"))
        print("NONE", gid, name, flush=True)
        continue
    d = os.path.join(OUT, "%03d_%s" % (gid, safe(name)))
    os.makedirs(d, exist_ok=True)
    lines = ["#EXTM3U"]
    for t, u in picked:
        lines += ["#EXTINF:" + t, u]
    data = "\n".join(lines) + "\n"
    open(os.path.join(d, "genre.m3u"), "w", encoding="ascii", errors="replace").write(data)
    manifest.append({"id": gid, "genre": name, "tags": used, "stations": len(picked), "bytes": len(data.encode())})
    print(i, gid, name, len(picked), ",".join(used), flush=True)

json.dump(manifest, open(os.path.join(WORK, "radiobrowser_manifest_genres.json"), "w"), indent=1)
json.dump(errors, open(os.path.join(WORK, "radiobrowser_errors_genres.json"), "w"), indent=1)
total = sum(m["bytes"] for m in manifest)
stations = sum(m["stations"] for m in manifest)
print("GENRES", len(manifest), "STATIONS", stations, "BYTES", total, "KB", round(total / 1024, 1))
print("ERRORS", len(errors), errors[:10])
