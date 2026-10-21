"""Keep every channel's stream link working without anyone touching it.

Runs hourly from .github/workflows/streams.yml. GitHub's runners are outside Turkey, so a channel that is
geo-blocked abroad (TRT 1 during some matches) looks broken from there; the last link is then kept. For each channel it tries, in order: the link in use
now, links found on the channel's own live page, and links from the community iptv-org list. A link
counts as working when its playlist and newest video segment download, and no host on the way uses a
Let's Encrypt certificate (the TV's 2017 browser rejects those). Links carrying an expiry (`e=` epoch,
NOW's tokens) are replaced before they run out. The result is written to streams.json and channels.js.

Usage: python3 tools/update_streams.py   (from the repo root)
"""
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
IPTV_ORG = "https://iptv-org.github.io/iptv/countries/tr.m3u"
# Replace expiring links this long before they run out; the job runs hourly.
EXPIRY_MARGIN = 2 * 3600
# Only the broadcasters' own CDNs: the iptv-org list also carries third-party restreams we don't want.
OFFICIAL_HOSTS = (".trt.com.tr", ".daioncdn.net", ".ercdn.net", ".duhnet.tv")

# preferred: the link to use while it works (1080p where the broadcaster offers a fixed one; otherwise
# the full playlist so the TV can pick up to 1080p). page/page_host: where to look for a fresh link.
# iptv: the channel's tvg-id prefix in the iptv-org list.
CHANNELS = [
    {"id": "trt1", "name": "TRT 1", "color": "#1d4fa3",
     "preferred": "https://tv-trt1.medya.trt.com.tr/master_1080.m3u8", "iptv": "TRT1.tr"},
    {"id": "atv", "name": "ATV", "color": "#c8102e",
     "preferred": "https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/atv/atv_1080p.m3u8",
     "page": "https://www.atv.com.tr/canli-yayin", "iptv": "ATV.tr"},
    {"id": "showtv", "name": "Show TV", "color": "#e85d04",
     "preferred": "https://ciner.daioncdn.net/showtv/showtv.m3u8?ce=3&app=4bc856ef-4c68-4a94-bc87-37dfaaa66558",
     "page": "https://www.showtv.com.tr/canli-yayin", "page_host": "ciner.daioncdn.net", "iptv": "ShowTV.tr"},
    {"id": "kanald", "name": "Kanal D", "color": "#0a6ebd",
     "preferred": "https://demiroren.daioncdn.net/kanald/kanald.m3u8?app=kanald_web&ce=3",
     "page": "https://www.kanald.com.tr/canli-yayin", "page_host": "demiroren.daioncdn.net", "iptv": "KanalD.tr"},
    {"id": "now", "name": "NOW", "color": "#d4145a",
     "page": "https://www.nowtv.com.tr/canli-yayin", "page_host": "nowtv.daioncdn.net", "iptv": "NOW.tr"},
    {"id": "startv", "name": "Star TV", "color": "#6a1b9a",
     "preferred": "https://dogus.daioncdn.net/startv/startv.m3u8?app=a20ac41e-bdc3-4aa1-934d-26b484480ac9&ce=3",
     "page": "https://www.startv.com.tr/canli-yayin", "page_host": "dogus.daioncdn.net", "iptv": "StarTV.tr"},
    {"id": "tv8", "name": "TV8", "color": "#2e7d32",
     "preferred": "https://tv8.daioncdn.net/tv8/tv8.m3u8?app=7ddc255a-ef47-4e81-ab14-c0e5f2949788&ce=3",
     "page": "https://www.tv8.com.tr/canli-yayin", "page_host": "tv8.daioncdn.net", "iptv": "TV8.tr"},
    {"id": "ntv", "name": "NTV", "color": "#37474f",
     "preferred": "https://dogus.daioncdn.net/ntv/ntv.m3u8?app=ntv_web",
     "page": "https://www.ntv.com.tr/canli-yayin/ntv", "page_host": "dogus.daioncdn.net", "iptv": "NTV.tr"},
    {"id": "trthaber", "name": "TRT Haber", "color": "#00838f",
     "preferred": "https://tv-trthaber.medya.trt.com.tr/master_1080.m3u8", "iptv": "TRTHaber.tr"},
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "streams.json")
OUTPUT = os.path.join(ROOT, "channels.js")

_issuer_cache = {}


def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read()


def issuer_org(host):
    """Organisation that issued the host's certificate, or None if unreachable."""
    if host not in _issuer_cache:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as tls:
                    issuer = dict(x[0] for x in tls.getpeercert()["issuer"])
            _issuer_cache[host] = issuer.get("organizationName", "")
        except Exception:
            _issuer_cache[host] = None
    return _issuer_cache[host]


def tv_trusts(url):
    host = urllib.parse.urlparse(url).hostname
    org = issuer_org(host)
    return org is not None and "Let's Encrypt" not in org


def expires_soon(url):
    e = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("e")
    return bool(e) and e[0].isdigit() and int(e[0]) - time.time() < EXPIRY_MARGIN


def media_lines(body):
    return [l.strip() for l in body.decode("utf8", "replace").splitlines() if l.strip() and not l.startswith("#")]


def works(url):
    """True when the playlist, its best rendition and the newest segment all download from trusted hosts."""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
        if not host.endswith(OFFICIAL_HOSTS) or expires_soon(url) or not tv_trusts(url):
            return False
        final, body = get(url)
        if b"#EXTM3U" not in body:
            return False
        text = body.decode("utf8", "replace")
        if "#EXT-X-STREAM-INF" in text:
            # Master playlist: follow the highest rendition up to 1080p, as the TV would.
            best, best_h = None, -1
            lines = text.splitlines()
            for i, line in enumerate(lines):
                m = re.search(r"RESOLUTION=\d+x(\d+)", line)
                if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                    h = int(m.group(1)) if m else 0
                    if best_h < h <= 1080:
                        best, best_h = lines[i + 1].strip(), h
            variant = urllib.parse.urljoin(final, best or media_lines(body)[0])
            if not tv_trusts(variant):
                return False
            final, body = get(variant)
        segments = media_lines(body)
        if not segments:
            return False
        seg = urllib.parse.urljoin(final, segments[-1])
        if not tv_trusts(seg):
            return False
        _, data = get(seg, timeout=25)
        return len(data) > 10000
    except Exception:
        return False


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


def main():
    state = {}
    if os.path.exists(STATE):
        with open(STATE) as f:
            state = json.load(f)
    try:
        playlist = get(IPTV_ORG)[1].decode("utf8", "replace")
    except Exception:
        playlist = ""

    result, report = {}, []
    for ch in CHANNELS:
        current = state.get(ch["id"])
        candidates = []
        for u in [ch.get("preferred"), current] + from_page(ch) + from_iptv(ch, playlist):
            if u and u not in candidates:
                candidates.append(u)
        chosen = next((u for u in candidates if works(u)), None)
        if chosen is None and current:
            # Nothing works right now (maybe a blip on the runner); keep the last link rather than drop the tile.
            chosen = current
            report.append("%-9s NO WORKING LINK, kept the old one" % ch["id"])
        elif chosen is None:
            report.append("%-9s NO WORKING LINK, tile hidden" % ch["id"])
        else:
            report.append("%-9s %s %s" % (ch["id"], "same" if chosen == current else "NEW ", chosen[:90]))
        if chosen:
            result[ch["id"]] = chosen

    print("\n".join(report))
    with open(STATE, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    tiles = [{"id": c["id"], "name": c["name"], "color": c["color"], "stream": result[c["id"]]}
             for c in CHANNELS if c["id"] in result]
    with open(OUTPUT, "w") as f:
        f.write("// Generated by tools/update_streams.py, which checks and repairs these links every hour.\n")
        f.write("// Edit the channel list there, not here.\n")
        f.write("var CHANNELS = %s;\n" % json.dumps(tiles, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
