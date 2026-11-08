"""Keep every channel's list of stream links healthy without anyone touching it.

Each channel has an ordered list of links. The TV's player (watch.html) starts with the first and moves
to the next by itself when one errors or freezes, so this job does not need to pick "the" working link.
It does three things, from .github/workflows/streams.yml:
  1. Renews NOW's link, whose token lasts about 4 hours, from the channel's live page.
  2. Adds fresh links from the channel's page and the iptv-org list when every known link is dead.
  3. Reports which links work, in the job summary.

GitHub's runners are outside Turkey and some links may refuse foreign visitors, or simply answer slowly,
so a failure here does not prove the link is dead for the TV. Known links are never removed.
GitHub also runs "hourly" schedules only every 3 to 17 hours in practice, so NOW keeps a token-free backup.

Usage: python3 tools/update_streams.py   (from the repo root)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
IPTV_ORG = "https://iptv-org.github.io/iptv/countries/tr.m3u"
# Renew expiring links this long before they run out.
EXPIRY_MARGIN = 2 * 3600
# Some playlists take over 20 seconds to answer, then work fine.
TIMEOUT = 30
MAX_LINKS = 6
# Only the broadcasters' own CDNs: the iptv-org list also carries third-party restreams we don't want.
OFFICIAL_HOSTS = (".trt.com.tr", ".daioncdn.net", ".ercdn.net", ".duhnet.tv")

DAION_SHOW = "https://ciner.daioncdn.net/showtv/showtv%s.m3u8?ce=3&app=4bc856ef-4c68-4a94-bc87-37dfaaa66558"
DAION_KANALD = "https://demiroren.daioncdn.net/kanald/kanald%s.m3u8?app=kanald_web&ce=3"
DAION_STAR = "https://dogus.daioncdn.net/startv/startv%s.m3u8?app=a20ac41e-bdc3-4aa1-934d-26b484480ac9&ce=3"
DAION_TV8 = "https://tv8.daioncdn.net/tv8/tv8%s.m3u8?app=7ddc255a-ef47-4e81-ab14-c0e5f2949788&ce=3"
DAION_NTV = "https://dogus.daioncdn.net/ntv/ntv%s.m3u8?app=ntv_web"
ERCDN_ATV = "https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/atv/atv_%s.m3u8"
TRT = "https://tv-%s.medya.trt.com.tr/master_%s.m3u8"

# links: tried in this order, best quality first: fixed 1080p, then the broadcaster's adaptive playlist, then 720p.
# The player falls back down the list and climbs back up. Star TV's top rendition is 720p.
# page/page_host: where to look for fresh links. iptv: the channel's tvg-id prefix in the iptv-org list.
# token_first: a page link with a token goes ahead of the fixed links.
CHANNELS = [
    {"id": "trt1", "name": "TRT 1", "color": "#1d4fa3", "iptv": "TRT1.tr",
     "links": [TRT % ("trt1", "1080"), TRT % ("trt1", "720"), TRT % ("trt1", "480")]},
    {"id": "atv", "name": "ATV", "color": "#c8102e", "iptv": "ATV.tr", "page": "https://www.atv.com.tr/canli-yayin",
     "links": [ERCDN_ATV % "1080p", ERCDN_ATV % "720p"]},
    {"id": "showtv", "name": "Show TV", "color": "#e85d04", "iptv": "ShowTV.tr",
     "page": "https://www.showtv.com.tr/canli-yayin", "page_host": "ciner.daioncdn.net",
     "links": [DAION_SHOW % "_1080p", DAION_SHOW % "", DAION_SHOW % "_720p"]},
    {"id": "kanald", "name": "Kanal D", "color": "#0a6ebd", "iptv": "KanalD.tr",
     "page": "https://www.kanald.com.tr/canli-yayin", "page_host": "demiroren.daioncdn.net",
     # duhnet is a separate CDN from the other two, so it survives a daioncdn outage.
     "links": [DAION_KANALD % "_1080p", DAION_KANALD % "", DAION_KANALD % "_720p", "https://kdlive.duhnet.tv/S2/HLS_LIVE/kanalddainp/playlist.m3u8"]},
    {"id": "now", "name": "NOW", "color": "#d4145a", "iptv": "NOW.tr", "token_first": True,
     "page": "https://www.nowtv.com.tr/canli-yayin", "page_host": "nowtv.daioncdn.net",
     "links": ["https://uycyyuuzyh.turknet.ercdn.net/nphindgytw/nowtv/nowtv_720p.m3u8"]},
    {"id": "startv", "name": "Star TV", "color": "#6a1b9a", "iptv": "StarTV.tr",
     "page": "https://www.startv.com.tr/canli-yayin", "page_host": "dogus.daioncdn.net",
     "links": [DAION_STAR % "", DAION_STAR % "_720p"]},
    {"id": "tv8", "name": "TV8", "color": "#2e7d32", "iptv": "TV8.tr",
     "page": "https://www.tv8.com.tr/canli-yayin", "page_host": "tv8.daioncdn.net",
     "links": [DAION_TV8 % "_1080p", DAION_TV8 % "", DAION_TV8 % "_720p"]},
    {"id": "ntv", "name": "NTV", "color": "#37474f", "iptv": "NTV.tr",
     "page": "https://www.ntv.com.tr/canli-yayin/ntv", "page_host": "dogus.daioncdn.net",
     "links": [DAION_NTV % "_1080p", DAION_NTV % "", DAION_NTV % "_720p"]},
    {"id": "trthaber", "name": "TRT Haber", "color": "#00838f", "iptv": "TRTHaber.tr",
     "links": [TRT % ("trthaber", "1080"), TRT % ("trthaber", "720"), TRT % ("trthaber", "480")]},
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "streams.json")
OUTPUT = os.path.join(ROOT, "channels.js")

def get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read()


def expires_soon(url):
    e = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("e")
    return bool(e) and e[0].isdigit() and int(e[0]) - time.time() < EXPIRY_MARGIN


def media_lines(body):
    return [l.strip() for l in body.decode("utf8", "replace").splitlines() if l.strip() and not l.startswith("#")]


def check(url):
    """True when the playlist, its best rendition up to 1080p and the newest segment all download."""
    final, body = get(url)
    if b"#EXTM3U" not in body:
        return False
    text = body.decode("utf8", "replace")
    if "#EXT-X-STREAM-INF" in text:
        best, best_h = None, -1
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.search(r"RESOLUTION=\d+x(\d+)", line)
            if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                h = int(m.group(1)) if m else 0
                if best_h < h <= 1080:
                    best, best_h = lines[i + 1].strip(), h
        final, body = get(urllib.parse.urljoin(final, best or media_lines(body)[0]))
    segments = media_lines(body)
    if not segments:
        return False
    _, data = get(urllib.parse.urljoin(final, segments[-1]))
    return len(data) > 10000


def works(url):
    host = urllib.parse.urlparse(url).hostname or ""
    if not host.endswith(OFFICIAL_HOSTS) or expires_soon(url):
        return False
    # Two tries: the slow playlists time out now and then and answer fine moments later.
    for _ in range(2):
        try:
            if check(url):
                return True
        except Exception:
            pass
    return False


def same_stream(a, b):
    """Same host and path: differs only in tokens, so not a real backup."""
    pa, pb = urllib.parse.urlparse(a), urllib.parse.urlparse(b)
    return (pa.hostname, pa.path) == (pb.hostname, pb.path)


def from_page(ch):
    if not ch.get("page"):
        return []
    try:
        _, body = get(ch["page"])
    except Exception:
        return []
    text = body.decode("utf8", "replace").replace("\\/", "/").replace("&amp;", "&")
    urls = re.findall(r"https?://[^\"'<>\s]+?\.m3u8[^\"'<>\s]*", text)
    host = ch.get("page_host")
    found = []
    for u in urls:
        if host and urllib.parse.urlparse(u).hostname != host:
            continue
        found.append(u)
        # Pages also embed stale tokens that the CDN ignores; keep a copy without them to try too.
        q = urllib.parse.parse_qsl(urllib.parse.urlparse(u).query)
        bare = [(k, v) for k, v in q if k not in ("st", "e")]
        if len(bare) != len(q):
            found.append(urllib.parse.urlunparse(urllib.parse.urlparse(u)._replace(query=urllib.parse.urlencode(bare))))
    return found


def from_iptv(ch, playlist):
    found = []
    lines = playlist.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and 'tvg-id="%s' % ch["iptv"] in line and i + 1 < len(lines):
            found.append(lines[i + 1].strip())
    return found


def links_for(ch, old, playlist):
    """The channel's ordered links, and a short health report."""
    fixed = ch["links"]
    with ThreadPoolExecutor(8) as pool:
        alive = list(pool.map(works, fixed))
    extra = []
    if ch.get("token_first") or not any(alive):
        # A still-valid link from last time first, so tokens only change when they must.
        seen = [u for u in old if u not in fixed] + from_page(ch) + from_iptv(ch, playlist)
        for u in seen:
            if not any(same_stream(u, k) for k in fixed + extra) and works(u):
                extra.append(u)
    links = extra + fixed if ch.get("token_first") else fixed + extra
    report = "%d/%d known links work" % (sum(alive), len(fixed))
    if extra:
        report += ", %d fresh link%s" % (len(extra), "" if len(extra) == 1 else "s")
    if not any(alive) and not extra:
        report += ", NOTHING works from here (may be blocked outside Turkey)"
    return links[:MAX_LINKS], report


def main():
    state = {}
    if os.path.exists(STATE):
        with open(STATE) as f:
            state = json.load(f)
    try:
        playlist = get(IPTV_ORG)[1].decode("utf8", "replace")
    except Exception:
        playlist = ""

    result = {}
    for ch in CHANNELS:
        old = state.get(ch["id"], [])
        old = [old] if isinstance(old, str) else old
        result[ch["id"]], report = links_for(ch, old, playlist)
        print("%-9s %s" % (ch["id"], report))

    with open(STATE, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    tiles = [{"id": c["id"], "name": c["name"], "color": c["color"], "streams": result[c["id"]]} for c in CHANNELS]
    with open(OUTPUT, "w") as f:
        f.write("// Generated by tools/update_streams.py. Edit the channel list there, not here.\n")
        f.write("var CHANNELS = %s;\n" % json.dumps(tiles, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
