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
BASE = os.path.dirname(os.path.abspath(__file__))          # scripts/
ROOT = os.path.dirname(os.path.dirname(BASE))               # repo root
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


def main():
    req = urllib.request.Request(RSS, headers=UA)
    xml = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    entries = re.findall(
        r"<entry>\s*<id>yt:video:([^<]+)</id>.*?<title>([^<]*)</title>"
        r".*?<published>([^<]+)</published>",
        xml,
        re.S,
    )
    videos = [
        (vid, html.unescape(title),
         datetime.datetime.fromisoformat(pub.replace("Z", "+00:00")).date())
        for vid, title, pub in entries[:COUNT]
    ]
    if len(videos) < COUNT:
        raise SystemExit(f"only {len(videos)} videos in feed, aborting")

    today = datetime.date.today()
    os.makedirs(THUMBS, exist_ok=True)
    for vid, _, _ in videos:
        dest = os.path.join(THUMBS, f"{vid}.jpg")
        if not os.path.exists(dest):
            req = urllib.request.Request(
                f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r, \
                    open(dest, "wb") as f:
                f.write(r.read())
    # prune thumbs of videos that fell out of the list
    keep = {f"{vid}.jpg" for vid, _, _ in videos}
    for name in os.listdir(THUMBS):
        if name.endswith(".jpg") and name not in keep:
            os.remove(os.path.join(THUMBS, name))

    cards = []
    for i, (vid, title, pub) in enumerate(videos, 1):
        cards.append(
            f'    <a class="vcard" href="https://www.youtube.com/watch?v={vid}">\n'
            f'      <div class="shot"><canvas id="v{i}" width="384" height="216">'
            f"</canvas><div class=\"foil\"></div></div>\n"
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
