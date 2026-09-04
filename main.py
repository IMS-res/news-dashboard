#!/usr/bin/env python3
# =============================================================================
#  NEWS & DATA DASHBOARD
#  Builds one webpage (index.html) with:
#    - Local news by category (economy, company/sector, politics)
#    - World & global-markets news + commodities
#    - A live market snapshot (major indices + commodities levels)
#    - Latest PBS & SBP economic releases
#    - Alerts (a GitHub issue -> email) whenever PBS/SBP post something new
#
#  You only ever edit the CONFIG sections. Everything else runs by itself.
# =============================================================================

import re
import os
import json
import html
import datetime
import feedparser
import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
#  CONFIG 1 - NEWS FEEDS, grouped into the categories shown on the page.
#  Add/remove a source by copying or deleting a line (keep the quotes + comma).
# -----------------------------------------------------------------------------
FEEDS = {
    "Domestic Economic News": [
        ("Business Recorder", "https://www.brecorder.com/feeds/latest-news"),
        ("Dawn - Business",   "https://www.dawn.com/feeds/business"),
    ],
    "Company & Sector News": [
        ("ProPakistani",      "https://propakistani.pk/feed/"),
        ("Tribune - Business","https://tribune.com.pk/feed/business"),
    ],
    "Domestic Political News": [
        ("Dawn - Pakistan",   "https://www.dawn.com/feeds/pakistan"),
        ("The News",          "https://www.thenews.com.pk/rss/1/1"),
        ("Tribune - Pakistan","https://tribune.com.pk/feed/pakistan"),
    ],
    "World & Geopolitics": [
        ("Dawn - World",      "https://www.dawn.com/feeds/world"),
        ("BBC World",         "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera",        "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
    "Global Markets & Commodities": [
        ("CNBC - Wall Street",  "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
        ("CNBC - Market Insider","https://www.cnbc.com/id/20409666/device/rss/rss.html"),
        ("CNBC - Energy",        "https://www.cnbc.com/id/19836768/device/rss/rss.html"),
        ("Investing - Commodities","https://www.investing.com/rss/news_11.rss"),
    ],
}

ITEMS_PER_SOURCE = 6        # headlines shown per news source
NEW_BADGE_HOURS = 24        # a headline newer than this gets a NEW badge

# -----------------------------------------------------------------------------
#  CONFIG 2 - MARKET SNAPSHOT (actual index & commodity levels, via Stooq).
#  Indices start with ^, commodities end with .f, currencies are 6 letters.
#  Values are end-of-day / delayed - fine for a dashboard, not for trading.
# -----------------------------------------------------------------------------
MARKET_SNAPSHOT = {
    "Indices": [
        ("S&P 500", "^spx"), ("Nasdaq", "^ndq"), ("Dow Jones", "^dji"),
        ("FTSE 100", "^uk100"), ("DAX", "^dax"),
        ("Nikkei 225", "^nkx"), ("Hang Seng", "^hsi"),
    ],
    "Commodities": [
        ("WTI Crude", "cl.f"), ("Brent Crude", "cb.f"), ("Gold", "gc.f"),
        ("Silver", "si.f"), ("Natural Gas", "ng.f"), ("Copper", "hg.f"),
    ],
    "Currencies": [
        ("USD / PKR", "usdpkr"), ("EUR / USD", "eurusd"),
    ],
}

# -----------------------------------------------------------------------------
#  CONFIG 3 - GOVERNMENT DATA (PBS + SBP) and ALERTS.
# -----------------------------------------------------------------------------
GOV_SOURCES = [
    {
        "category": "Economic Data - PBS (Bureau of Statistics)",
        "name": "PBS latest releases",
        "url": "https://www.pbs.gov.pk/",
        "priority": ["inflation", "trade", "spi", "cpi", "price", "manufacturing",
                     "qim", "report", "summary", "index", "survey", "account",
                     "gdp", "release"],
    },
    {
        "category": "Economic Data - SBP (State Bank)",
        "name": "SBP press releases",
        "url": "https://www.sbp.org.pk/press/index.htm",
        "priority": ["policy", "rate", "reserves", "monetary", "inflation",
                     "review", "statement", "reserve", "report", "release"],
    },
]
GOV_ITEMS = 12

# Your GitHub username - used to @mention you in the alert so you get an email.
# If this is wrong you simply won't get the mention; change it to match.
NOTIFY_USERNAME = "IMS-res"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-news-reader/1.0)"}

# =============================================================================
#  Machinery below - you can ignore it.
# =============================================================================
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_STOPWORDS = ("festival", "gallery", "event", "career", "job opening", "jobs",
              "tender", "museum", "sitemap", "privacy", "disclaimer", "login",
              "read more", "load more", "glossary", "help desk", "contact us",
              "about us", "home remittance")
_YEAR_RE = re.compile(r"\b20\d{2}\b")
_DATE_RE = re.compile(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _is_recent(struct_time):
    if not struct_time:
        return False
    try:
        published = datetime.datetime(*struct_time[:6], tzinfo=datetime.timezone.utc)
        return (_now() - published) <= datetime.timedelta(hours=NEW_BADGE_HOURS)
    except Exception:
        return False


def _looks_like_release(text):
    t = " ".join(text.split())
    low = t.lower()
    if len(t) < 18 or len(t.split()) < 3:
        return False
    if any(s in low for s in _STOPWORDS):
        return False
    return bool(_YEAR_RE.search(low) or _DATE_RE.search(low)
                or any(m in low for m in _MONTHS))


def fetch_rss(name, url):
    try:
        parsed = feedparser.parse(url, request_headers=HEADERS)
        items = []
        for entry in parsed.entries[:ITEMS_PER_SOURCE]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            when = entry.get("published_parsed") or entry.get("updated_parsed")
            items.append({"title": title, "link": link, "new": _is_recent(when),
                          "source": name})
        status = f"OK  {len(items):>2} items" if items else "NO ITEMS - check link"
        print(f"  [{status}]  {name}")
        return items
    except Exception as e:
        print(f"  [ERROR - {e}]  {name}")
        return []


def fetch_gov(source):
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        base = "/".join(source["url"].split("/")[:3])
        priority = source.get("priority", [])
        seen, found = set(), []
        for a in soup.find_all("a", href=True):
            text = " ".join(a.get_text().split())
            if not _looks_like_release(text):
                continue
            href = a["href"].strip()
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                href = source["url"].rsplit("/", 1)[0] + "/" + href
            if href in seen:
                continue
            seen.add(href)
            score = 1 if any(k in text.lower() for k in priority) else 0
            found.append((score, len(found),
                          {"title": text, "link": href, "new": False,
                           "source": source["name"]}))
        found.sort(key=lambda x: (-x[0], x[1]))
        items = [f[2] for f in found[:GOV_ITEMS]]
        status = f"OK  {len(items):>2} items" if items else "NO ITEMS - layout may have changed"
        print(f"  [{status}]  {source['name']}")
        return items
    except Exception as e:
        print(f"  [ERROR - {e}]  {source['name']}")
        return []


def fetch_quotes():
    """One request to Stooq for all symbols; returns section for the page."""
    pairs = [(g, n, s) for g, lst in MARKET_SNAPSHOT.items() for n, s in lst]
    symbols = ",".join(s for _, _, s in pairs)
    url = f"https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv"
    data = {}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        rows = [r for r in resp.text.splitlines() if r.strip()]
        for row in rows[1:]:                       # skip header
            c = row.split(",")
            if len(c) < 7:
                continue
            sym = c[0].lower()
            try:
                op, cl = float(c[3]), float(c[6])
            except ValueError:
                continue
            pct = ((cl - op) / op * 100) if op else 0.0
            data[sym] = (cl, pct)
        print(f"  [OK  {len(data):>2} quotes]  Market snapshot (Stooq)")
    except Exception as e:
        print(f"  [ERROR - {e}]  Market snapshot (Stooq)")

    items = []
    for group, name, sym in pairs:
        q = data.get(sym.lower())
        if not q:
            continue
        cl, pct = q
        val = f"{cl:,.2f}" if cl >= 1 else f"{cl:,.4f}"
        items.append({"kind": "quote", "group": group, "name": name,
                      "value": val, "pct": pct,
                      "link": f"https://stooq.com/q/?s={sym}"})
    return items


def process_alerts(gov_items):
    """Detect brand-new PBS/SBP releases; write alert.md for the workflow."""
    STATE, ALERT = "state.json", "alert.md"
    links = [g["link"] for g in gov_items]
    first_run = not os.path.exists(STATE)
    seen = set()
    if not first_run:
        try:
            seen = set(json.load(open(STATE)))
        except Exception:
            seen = set()
    new = [g for g in gov_items if g["link"] not in seen]
    updated = list(seen) + [l for l in links if l not in seen]
    json.dump(updated[-800:], open(STATE, "w"))

    if first_run:
        print("  First run - baseline saved, no alert sent.")
        return
    if new:
        mention = f"@{NOTIFY_USERNAME}\n\n" if NOTIFY_USERNAME else ""
        body = [mention, "New economic data release(s) detected:\n"]
        for g in new:
            body.append(f"- **{g['source']}**: [{g['title']}]({g['link']})")
        open(ALERT, "w").write("\n".join(body))
        print(f"  ALERT: {len(new)} new release(s) -> {ALERT}")
    else:
        print("  No new PBS/SBP releases this run.")


def build_page(sections):
    stamp = _now().strftime("%d %b %Y, %H:%M UTC")
    out = ["""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>News & Data Dashboard</title>
<style>
 :root{--bg:#0f1115;--card:#171a21;--line:#262b36;--txt:#e7e9ee;--dim:#9aa3b2;
   --accent:#4c8bf5;--new:#1f9d55;--up:#26a269;--down:#e5484d}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);
   font:16px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 header{padding:22px 20px;border-bottom:1px solid var(--line)}
 h1{margin:0;font-size:20px} .stamp{color:var(--dim);font-size:13px;margin-top:4px}
 main{max-width:1200px;margin:0 auto;padding:18px;display:grid;
   grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
 section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
 h2{margin:0 0 10px;font-size:15px;color:var(--accent);border-bottom:1px solid var(--line);padding-bottom:8px}
 .src{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.4px;margin:12px 0 4px}
 a.item{display:block;color:var(--txt);text-decoration:none;padding:6px 0;border-bottom:1px solid var(--line)}
 a.item:hover{color:var(--accent)} a.item:last-child{border-bottom:0}
 .badge{display:inline-block;background:var(--new);color:#fff;font-size:10px;font-weight:700;
   padding:1px 6px;border-radius:6px;margin-right:6px;vertical-align:middle}
 a.q{display:flex;justify-content:space-between;gap:10px;color:var(--txt);text-decoration:none;
   padding:6px 0;border-bottom:1px solid var(--line)}
 a.q:last-child{border-bottom:0} a.q .nm{color:var(--txt)}
 a.q .vv{font-variant-numeric:tabular-nums} .up{color:var(--up)} .down{color:var(--down)}
 footer{color:var(--dim);font-size:12px;text-align:center;padding:24px}
</style></head><body>
<header><h1>News &amp; Data Dashboard</h1>
<div class="stamp">Last updated: """ + stamp + """ &middot; refreshes automatically</div></header><main>"""]

    for title, items in sections:
        if not items:
            continue
        out.append(f'<section><h2>{html.escape(title)}</h2>')
        cur = None
        for it in items:
            if it.get("kind") == "quote":
                if it.get("group") != cur:
                    cur = it.get("group")
                    out.append(f'<div class="src">{html.escape(cur)}</div>')
                cls = "up" if it["pct"] >= 0 else "down"
                arrow = "\u25b2" if it["pct"] >= 0 else "\u25bc"
                out.append(
                    f'<a class="q" href="{html.escape(it["link"])}" target="_blank" rel="noopener">'
                    f'<span class="nm">{html.escape(it["name"])}</span>'
                    f'<span class="vv">{it["value"]} '
                    f'<span class="{cls}">{arrow}{abs(it["pct"]):.2f}%</span></span></a>')
            else:
                if it.get("source") != cur:
                    cur = it.get("source")
                    if cur:
                        out.append(f'<div class="src">{html.escape(cur)}</div>')
                badge = '<span class="badge">NEW</span>' if it.get("new") else ""
                out.append(
                    f'<a class="item" href="{html.escape(it["link"])}" target="_blank" '
                    f'rel="noopener">{badge}{html.escape(it["title"])}</a>')
        out.append("</section>")

    out.append('<footer>Personal, non-commercial dashboard. Market data via Stooq '
               '(delayed). Headlines link to their original publishers.</footer></main></body></html>')
    return "".join(out)


def main():
    sections = []

    # 1) Market snapshot first (the data panel).
    print("\nMarket snapshot")
    sections.append(("Market Snapshot (indices & commodities)", fetch_quotes()))

    # 2) All the news categories.
    for category, feeds in FEEDS.items():
        print(f"\n{category}")
        collected = []
        for name, url in feeds:
            collected.extend(fetch_rss(name, url))
        sections.append((category, collected))

    # 3) Government data (PBS + SBP) + alert detection.
    print("\nGovernment data")
    gov_items = []
    gov_sections = {}
    for src in GOV_SOURCES:
        items = fetch_gov(src)
        gov_items.extend(items)
        gov_sections.setdefault(src["category"], []).extend(items)
    for cat, items in gov_sections.items():
        sections.append((cat, items))
    process_alerts(gov_items)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_page(sections))
    total = sum(len(i) for _, i in sections)
    print(f"\nDONE. index.html written with {total} items.")


if __name__ == "__main__":
    main()
