import json, os, re, time, urllib.parse, urllib.request
WORK = os.environ.get("RB_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))

BASE = "https://de1.api.radio-browser.info/json/stations/search"
OUT = os.path.join(WORK, "radiobrowser_out")
COUNTRIES = os.path.join(WORK, "rb_countries.json")

def fetch(code, attempt=0):
    q = urllib.parse.urlencode({
        "countrycode": code,
        "codec": "MP3",
        "hidebroken": "true",
        "order": "votes",
        "reverse": "true",
        "limit": "40",
    })
    req = urllib.request.Request(BASE + "?" + q, headers={"User-Agent": "reciva-import/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)

def safe(s):
    s = re.sub(r'[\x00-\x1f/\\:*?"<>|]', '', s).strip()
    s = re.sub(r'\s+', ' ', s)
    return s[:40].rstrip(' .')

def clean_title(s):
    s = re.sub(r'[\x00-\x1f\r\n]', ' ', s or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:48]

countries = json.load(open(COUNTRIES))
os.makedirs(OUT, exist_ok=True)
manifest = []
errors = []
for i, c in enumerate(countries, 1):
    code = c["iso_3166_1"]
    name = c["name"]
    try:
        rows = fetch(code)
    except Exception as e:
        errors.append((code, name, repr(e)))
        continue
    picked = []
    seen = set()
    for st in rows:
        url = (st.get("url_resolved") or st.get("url") or "").strip()
        if not url.lower().startswith("http://"):
            continue
        if url in seen:
            continue
        seen.add(url)
        picked.append((clean_title(st.get("name") or code), url))
        if len(picked) == 10:
            break
    if not picked:
        errors.append((code, name, "no http mp3 stations"))
        continue
    d = os.path.join(OUT, safe(name))
    os.makedirs(d, exist_ok=True)
    lines = ["#EXTM3U"]
    for title, url in picked:
        lines.append("#EXTINF:" + title)
        lines.append(url)
    data = "\n".join(lines) + "\n"
    fn = os.path.join(d, safe(name) + ".m3u")
    open(fn, "w", encoding="ascii", errors="replace").write(data)
    manifest.append({"code": code, "country": name, "dir": safe(name), "stations": len(picked), "bytes": len(data.encode())})
    if i % 25 == 0:
        print("processed", i, flush=True)

json.dump(manifest, open(os.path.join(WORK, "radiobrowser_manifest.json"), "w"), indent=1)
json.dump(errors, open(os.path.join(WORK, "radiobrowser_errors.json"), "w"), indent=1)
total = sum(m["bytes"] for m in manifest)
stations = sum(m["stations"] for m in manifest)
print("COUNTRIES", len(manifest), "STATIONS", stations, "BYTES", total, "KB", round(total/1024,1))
print("ERRORS", len(errors))
for e in errors[:20]: print(" ", e)
