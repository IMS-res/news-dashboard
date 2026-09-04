#!/usr/bin/env python3
# =============================================================================
#  NEWS & DATA DASHBOARD  -  builds one webpage (index.html) with the latest
#  headlines from your news sites + latest releases from PBS and SBP.
#
#  You do NOT need to understand this code. You only ever edit the CONFIG
#  section just below if you want to add/remove a source. Everything else
#  runs by itself.
# =============================================================================

import sys
import html
import datetime
import feedparser
import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
#  CONFIG  --  the only part you might ever touch.
#
#  This is your list of news feeds, grouped into categories (the headings you
#  will see on the page). To add a source, copy a line and change the name and
#  link. To remove one, delete its line. Keep the quotes and the comma.
#
#  These RSS links were verified to work. If you add your own and it shows
#  "no items" in the run log, the link is wrong -- see the README for how to
#  find a site's real RSS link.
# -----------------------------------------------------------------------------
FEEDS = {
    "Pakistan - Business & Economy": [
        ("Business Recorder", "https://www.brecorder.com/feeds/latest-news"),
        ("Dawn - Business",   "https://www.dawn.com/feeds/business"),
        ("Tribune - Business","https://tribune.com.pk/feed/business"),
        ("ProPakistani",      "https://propakistani.pk/feed/"),
    ],
    "Pakistan - Top News": [
        ("Dawn",              "https://www.dawn.com/feeds/home"),
        ("The News",          "https://www.thenews.com.pk/rss/1/1"),
        ("Express Tribune",   "https://tribune.com.pk/feed/home"),
        ("The Nation",        "https://www.nation.com.pk/rss/newspaper"),
    ],
    "World": [
        ("Reuters World",     "https://feeds.reuters.com/Reuters/worldNews"),
        ("BBC World",         "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera",        "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
}

# How many headlines to show per source.
ITEMS_PER_SOURCE = 8

# A headline published within this many hours gets a "NEW" badge.
NEW_BADGE_HOURS = 24

# -----------------------------------------------------------------------------
#  Government data sources (PBS + SBP).
#  These are "What's New" style pages, not clean feeds, so we read the page and
#  pull out the recent links. If a source ever shows nothing, its website layout
#  changed -- that is the expected weak spot; the news feeds above are the solid
#  core. See the README.
# -----------------------------------------------------------------------------
GOV_SOURCES = [
    {
        "category": "Economic Data - PBS (Bureau of Statistics)",
        "name": "PBS latest releases",
        "url": "https://www.pbs.gov.pk/",
        # we look for links whose text mentions a report/release keyword
        "keywords": ["report", "index", "spi", "cpi", "inflation", "trade",
                     "release", "statistics", "survey", "bulletin", "qim"],
    },
    {
        "category": "Economic Data - SBP (State Bank)",
        "name": "SBP press releases",
        "url": "https://www.sbp.org.pk/press/index.htm",
        "keywords": ["press", "release", "policy", "rate", "reserves",
                     "circular", "statement", "monetary"],
    },
]

# A browser-like header so plain government pages don't reject the request.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-news-reader/1.0)"}


# =============================================================================
#  From here down is machinery. You can ignore it.
# =============================================================================

def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _is_recent(struct_time):
    """True if a feed item's date is within NEW_BADGE_HOURS."""
    if not struct_time:
        return False
    try:
        published = datetime.datetime(*struct_time[:6],
                                      tzinfo=datetime.timezone.utc)
        return (_now() - published) <= datetime.timedelta(hours=NEW_BADGE_HOURS)
    except Exception:
        return False


def fetch_rss(name, url):
    """Return a list of {title, link, new} for one RSS feed. Never crashes."""
    try:
        parsed = feedparser.parse(url, request_headers=HEADERS)
        items = []
        for entry in parsed.entries[:ITEMS_PER_SOURCE]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            when = entry.get("published_parsed") or entry.get("updated_parsed")
            items.append({"title": title, "link": link, "new": _is_recent(when)})
        status = f"OK  {len(items):>2} items" if items else "NO ITEMS - check link"
        print(f"  [{status}]  {name}")
        return items
    except Exception as e:
        print(f"  [ERROR - {e}]  {name}")
        return []


def fetch_gov(source):
    """Read a government 'what's new' page and pull recent report links."""
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=30, verify=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        base = "/".join(source["url"].split("/")[:3])  # e.g. https://www.pbs.gov.pk
        seen, items = set(), []
        for a in soup.find_all("a", href=True):
            text = " ".join(a.get_text().split())
            if len(text) < 12:
                continue
            low = text.lower()
            if not any(k in low for k in source["keywords"]):
                continue
            href = a["href"].strip()
            if href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                href = source["url"].rsplit("/", 1)[0] + "/" + href
            if href in seen:
                continue
            seen.add(href)
            items.append({"title": text, "link": href, "new": False})
            if len(items) >= ITEMS_PER_SOURCE:
                break
        status = f"OK  {len(items):>2} items" if items else "NO ITEMS - layout may have changed"
        print(f"  [{status}]  {source['name']}")
        return items
    except Exception as e:
        print(f"  [ERROR - {e}]  {source['name']}")
        return []


def build_page(sections):
    """sections = list of (category_title, [items]). Returns HTML string."""
    stamp = _now().strftime("%d %b %Y, %H:%M UTC")
    parts = ["""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>News & Data Dashboard</title>
<style>
 :root{--bg:#0f1115;--card:#171a21;--line:#262b36;--txt:#e7e9ee;--dim:#9aa3b2;--accent:#4c8bf5;--new:#1f9d55}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);
   font:16px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 header{padding:22px 20px;border-bottom:1px solid var(--line)}
 h1{margin:0;font-size:20px} .stamp{color:var(--dim);font-size:13px;margin-top:4px}
 main{max-width:1100px;margin:0 auto;padding:18px;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
 section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
 h2{margin:0 0 10px;font-size:15px;color:var(--accent);border-bottom:1px solid var(--line);padding-bottom:8px}
 .src{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.4px;margin:12px 0 4px}
 a.item{display:block;color:var(--txt);text-decoration:none;padding:6px 0;border-bottom:1px solid var(--line)}
 a.item:hover{color:var(--accent)} a.item:last-child{border-bottom:0}
 .badge{display:inline-block;background:var(--new);color:#fff;font-size:10px;font-weight:700;
   padding:1px 6px;border-radius:6px;margin-right:6px;vertical-align:middle}
 footer{color:var(--dim);font-size:12px;text-align:center;padding:24px}
</style></head><body>
<header><h1>News &amp; Data Dashboard</h1>
<div class="stamp">Last updated: """ + stamp + """ &nbsp;&middot;&nbsp; refreshes automatically</div></header><main>"""]

    for title, items in sections:
        if not items:
            continue
        parts.append(f"<section><h2>{html.escape(title)}</h2>")
        current_src = None
        for it in items:
            if it.get("source") != current_src:
                current_src = it.get("source")
                if current_src:
                    parts.append(f'<div class="src">{html.escape(current_src)}</div>')
            badge = '<span class="badge">NEW</span>' if it.get("new") else ""
            t = html.escape(it["title"])
            parts.append(f'<a class="item" href="{html.escape(it["link"])}" '
                         f'target="_blank" rel="noopener">{badge}{t}</a>')
        parts.append("</section>")

    parts.append('<footer>Personal, non-commercial news reader. '
                 'Headlines link to their original sources.</footer></main></body></html>')
    return "".join(parts)


def main():
    sections = []

    for category, feeds in FEEDS.items():
        print(f"\n{category}")
        collected = []
        for name, url in feeds:
            for it in fetch_rss(name, url):
                it["source"] = name
                collected.append(it)
        sections.append((category, collected))

    # Government sources, each becomes its own section.
    gov_by_cat = {}
    print("\nGovernment data")
    for src in GOV_SOURCES:
        items = fetch_gov(src)
        for it in items:
            it["source"] = src["name"]
        gov_by_cat.setdefault(src["category"], []).extend(items)
    for cat, items in gov_by_cat.items():
        sections.append((cat, items))

    page = build_page(sections)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    total = sum(len(items) for _, items in sections)
    print(f"\nDONE. Wrote index.html with {total} items across "
          f"{len([s for s in sections if s[1]])} sections.")


if __name__ == "__main__":
    main()
