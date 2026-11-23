#!/usr/bin/env python3
"""Fetch latest YouTube videos and rewrite the videos block in docs/index.html.

Reads the channel RSS feed, takes the 6 newest videos, downloads their
thumbnails into docs/assets/thumbs/, and replaces everything between
<!-- VIDEOS:START --> and <!-- VIDEOS:END --> with fresh cards.
Run daily via .github/workflows/videos.yml; safe to run manually.
"""
import datetime
import html
import os
import re
import urllib.request

CHANNEL_ID = "UC9GCAvy2MyxhYoMB2L3Tb4A"
COUNT = 6
# Optional: a YouTube Data API v3 key (repo secret YOUTUBE_API_KEY).
# Page scraping of watch/embed pages works from home IPs but is blocked
# from GitHub runners (no lengthSeconds served) — so on CI the key is
# the only way to detect shorts. Without it the script aborts loudly
# instead of silently restoring shorts (fail-closed).
API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
HERE = os.path.dirname(os.path.abspath(__file__))   # .../.github/scripts
ROOT = os.path.dirname(os.path.dirname(HERE))       # repo root (.../.github -> ...)
PAGE = os.path.join(ROOT, "docs", "index.html")
THUMBS = os.path.join(ROOT, "docs", "assets", "thumbs")
RSS = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
UA = {"User-Agent": "Mozilla/5.0 (artition-site videos updater)"}


def plural(n, forms):
    n = abs(n) % 100
    d = n % 10
    if 10 < n < 20:
        return forms[2]
    if d > 1 and d < 5:
        return forms[1]
    if d == 1:
        return forms[0]
    return forms[2]


def rel_date(pub, today):
    days = (today - pub).days
    if days < 1:
        return "сегодня"
    if days < 7:
        return f"{days} {plural(days, ['день', 'дня', 'дней'])} назад"
    if days < 31:
        w = round(days / 7)
        return f"{w} {plural(w, ['неделю', 'недели', 'недель'])} назад"
    months = (today.year - pub.year) * 12 + (today.month - pub.month)
    if months < 12:
        return f"{months} {plural(months, ['месяц', 'месяца', 'месяцев'])} назад"
    y = round(months / 12)
    return f"{y} {plural(y, ['год', 'года', 'лет'])} назад"


def iso_seconds(s):
    """Parse an ISO-8601 duration (PT2M5S) into seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", s or "")
    if not m:
        return None
    h, mnt, sec = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mnt * 60 + sec


def fmt_dur(secs):
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fetch_seconds(vid):
    """Length of a video in seconds, or None if undetectable.

    Tries the watch page first, then the embed page (less bot-guarded
    from datacenter IPs). Callers must treat None as "unknown" — never
    as "long" (fail-closed, otherwise shorts silently slip back in).
    """
    urls = (f"https://www.youtube.com/watch?v={vid}",
            f"https://www.youtube.com/embed/{vid}")
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=UA)
            page = urllib.request.urlopen(req, timeout=30).read().decode(
                "utf-8", "ignore")
            m = re.search(r'"lengthSeconds":"(\d+)"', page)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


def main():
    req = urllib.request.Request(RSS, headers=UA)
    xml = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    entries = re.findall(
        r"<entry>\s*<id>yt:video:([^<]+)</id>.*?<title>([^<]*)</title>"
        r".*?<published>([^<]+)</published>",
        xml,
        re.S,
    )
    videos = []
    api_cache = {}
    if API_KEY:
        # One batched call for the whole feed (id= supports up to 50).
        ids = [vid for vid, _, _ in entries[:50]]
        try:
            req = urllib.request.Request(
                "https://www.googleapis.com/youtube/v3/videos"
                f"?part=contentDetails&id={','.join(ids)}&key={API_KEY}",
                headers=UA)
            data = urllib.request.urlopen(
                req, timeout=30).read().decode("utf-8")
            for item in re.findall(
                    r'"id"\s*:\s*"([^"]+)"(.*?)"duration"\s*:\s*"([^"]+)"',
                    data, flags=re.S):
                api_cache[item[0]] = iso_seconds(item[2])
            print(f"api: parsed {len(api_cache)} durations")
        except Exception as e:
            print(f"api error: {e}")
    for vid, title, pub in entries:
        if len(videos) >= COUNT:
            break
        secs = api_cache[vid] if vid in api_cache else fetch_seconds(vid)
        if vid in api_cache:
            print(f"{vid}: {secs if secs is not None else 'unknown'}s (api)")
        else:
            print(f"{vid}: {secs if secs is not None else 'unknown'}s")
        if secs is None or secs < 60:
            continue  # shorts — or undetectable (fail-closed, never keep)
        videos.append((vid, html.unescape(title),
                       datetime.datetime.fromisoformat(
                           pub.replace("Z", "+00:00")).date(), secs))
    if len(videos) < COUNT:
        raise SystemExit(f"only {len(videos)} long videos in feed, aborting")

    today = datetime.date.today()
    os.makedirs(THUMBS, exist_ok=True)
    for vid, _, _, _ in videos:
        dest = os.path.join(THUMBS, f"{vid}.jpg")
        if not os.path.exists(dest):
            req = urllib.request.Request(
                f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r, \
                    open(dest, "wb") as f:
                f.write(r.read())
    # prune thumbs of videos that fell out of the list
    keep = {f"{vid}.jpg" for vid, _, _, _ in videos}
    for name in os.listdir(THUMBS):
        if name.endswith(".jpg") and name not in keep:
            os.remove(os.path.join(THUMBS, name))

    cards = []
    for i, (vid, title, pub, secs) in enumerate(videos, 1):
        cards.append(
            f'    <a class="vcard" href="https://www.youtube.com/watch?v={vid}">\n'
            f'      <div class="shot"><canvas id="v{i}" width="384" height="216">'
            f"</canvas><div class=\"foil\"></div>"
            f"<span class=\"vdur\">{fmt_dur(secs)}</span></div>\n"
            f"      <h3>{html.escape(title, quote=False)}</h3>\n"
            f'      <div class="vmeta"><span>{rel_date(pub, today)}</span></div>\n'
            f"    </a>"
        )
    block = ("  <!-- VIDEOS:START -->\n  <div class=\"vgrid\">\n"
             + "\n".join(cards)
             + "\n  </div>\n  <!-- VIDEOS:END -->")

    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    new_page, n = re.subn(
        r"  <!-- VIDEOS:START -->.*?  <!-- VIDEOS:END -->",
        lambda _: block, page, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("videos markers not found in docs/index.html")
    if new_page != page:
        with open(PAGE, "w", encoding="utf-8", newline="") as f:
            f.write(new_page)
        print(f"updated: {[v[0] for v in videos]}")
    else:
        print("no changes")


if __name__ == "__main__":
    main()
