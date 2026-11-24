import json, os, re, urllib.parse, urllib.request
WORK = os.environ.get("RB_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))

BASE = "https://de1.api.radio-browser.info/json/stations/search"
OUT = os.path.join(WORK, "radiobrowser_out_100")
COUNTRIES = os.path.join(WORK, "rb_countries.json")
EU = set("""AD AL AM AT AZ AU BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GE GR HR HU IE IS IT LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SK SM TR UA VA US""".split())
NAMES = {
    "GB": "England (UK)", "US": "USA", "AU": "Australien", "DE": "Deutschland",
    "AT": "Österreich", "CH": "Schweiz", "FR": "Frankreich", "IT": "Italien",
    "ES": "Spanien", "NL": "Niederlande", "PL": "Polen", "SE": "Schweden",
    "NO": "Norwegen", "DK": "Dänemark", "FI": "Finnland", "BE": "Belgien",
    "CZ": "Tschechien",
}
WANT = 100


def fetch(code, attempt=0):
    q = urllib.parse.urlencode({
        "countrycode": code, "codec": "MP3", "hidebroken": "true",
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


countries = [c for c in json.load(open(COUNTRIES)) if c["iso_3166_1"] in EU]
os.makedirs(OUT, exist_ok=True)
manifest, errors = [], []
for i, c in enumerate(countries, 1):
    code, name = c["iso_3166_1"], NAMES.get(c["iso_3166_1"], c["name"])
    try:
        rows = fetch(code)
    except Exception as e:
        errors.append((code, name, repr(e)))
        print("ERR", i, code, repr(e), flush=True)
        continue
    picked, seen = [], set()
    for st in rows:
        url = (st.get("url_resolved") or st.get("url") or "").strip()
        if not url.lower().startswith("http://") or url in seen:
            continue
        seen.add(url)
        picked.append((title(st.get("name") or code), url))
        if len(picked) == WANT:
            break
    if not picked:
        errors.append((code, name, "none"))
        continue
    d = os.path.join(OUT, safe(name))
    os.makedirs(d, exist_ok=True)
    lines = ["#EXTM3U"]
    for t, u in picked:
        lines += ["#EXTINF:" + t, u]
    data = "\n".join(lines) + "\n"
    open(os.path.join(d, safe(name) + ".m3u"), "w", encoding="ascii", errors="replace").write(data)
    manifest.append({"code": code, "country": name, "stations": len(picked), "bytes": len(data.encode())})
    print(i, code, name, len(picked), len(data), flush=True)

json.dump(manifest, open(os.path.join(WORK, "radiobrowser_manifest_100.json"), "w"), indent=1)
json.dump(errors, open(os.path.join(WORK, "radiobrowser_errors_100.json"), "w"), indent=1)
total = sum(m["bytes"] for m in manifest)
stations = sum(m["stations"] for m in manifest)
print("COUNTRIES", len(manifest), "STATIONS", stations, "BYTES", total, "KB", round(total / 1024, 1))
print("ERRORS", len(errors), errors[:10])
