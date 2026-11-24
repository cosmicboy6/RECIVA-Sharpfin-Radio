import json, os, re, urllib.parse, urllib.request
WORK = os.environ.get("RB_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))

BASE = "https://de1.api.radio-browser.info/json/stations/search"
OUT = os.path.join(WORK, "radiobrowser_out_eu")
COUNTRIES = os.path.join(WORK, "rb_countries.json")

EU = set("""AD AL AM AT AZ BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GE GR HR HU IE IS IT LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SK SM TR UA VA US""".split())

NAMES = {
    "GB": "England (UK)",
    "US": "USA",
    "DE": "Deutschland",
    "AT": "Österreich",
    "CH": "Schweiz",
    "FR": "Frankreich",
    "IT": "Italien",
    "ES": "Spanien",
    "NL": "Niederlande",
    "PL": "Polen",
    "SE": "Schweden",
    "NO": "Norwegen",
    "DK": "Dänemark",
    "FI": "Finnland",
    "BE": "Belgien",
    "CZ": "Tschechien",
    "AT": "Österreich",
    "GB": "England (UK)",
}
# English names for the rest (RadioBrowser names)

def fetch(code):
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
    return re.sub(r'\s+', ' ', s).strip()[:48]

countries = [c for c in json.load(open(COUNTRIES)) if c["iso_3166_1"] in EU]
os.makedirs(OUT, exist_ok=True)
manifest, errors = [], []

for i, c in enumerate(countries, 1):
    code = c["iso_3166_1"]
    name = NAMES.get(code, c["name"])
    try:
        rows = fetch(code)
    except Exception as e:
        errors.append((code, name, repr(e)))
        continue
    picked, seen = [], set()
    for st in rows:
        url = (st.get("url_resolved") or st.get("url") or "").strip()
        if not url.lower().startswith("http://") or url in seen:
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
        lines += ["#EXTINF:" + title, url]
    data = "\n".join(lines) + "\n"
    open(os.path.join(d, safe(name) + ".m3u"), "w", encoding="ascii", errors="replace").write(data)
    manifest.append({"code": code, "country": name, "dir": safe(name), "stations": len(picked), "bytes": len(data.encode())})
    print(i, code, name, len(picked), flush=True)

json.dump(manifest, open(os.path.join(WORK, "radiobrowser_manifest_eu.json"), "w"), indent=1)
json.dump(errors, open(os.path.join(WORK, "radiobrowser_errors_eu.json"), "w"), indent=1)
total = sum(m["bytes"] for m in manifest)
print("COUNTRIES", len(manifest), "STATIONS", sum(m["stations"] for m in manifest), "BYTES", total, "KB", round(total/1024,1))
print("ERRORS", len(errors), errors[:10])
