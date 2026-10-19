# polite-web-reader

Fetch web pages the way a good guest would, and get clean text and links back.

Before it asks for a page it reads the site's robots.txt and does what it says. It waits its turn
on each host, keeps a disk cache and asks "has this changed?" instead of downloading again, backs
off when the server says it's busy, and tells you when it was stopped by a bot check instead of
handing you the check page as if it were the content.

Python 3.10+, standard library only, about 500 lines.

**Run it** (no network; the demo serves a small site on 127.0.0.1):

```bash
python examples/demo.py
python -m unittest discover -s tests -t .
python -m polite_reader https://example.com
```

**Use it:**

```python
from polite_reader import Reader

reader = Reader(min_interval=1.0, max_age=3600)      # one Reader per crawl
page = reader.fetch("https://example.com/")
if page.ok:
    print(page.title, page.text[:200], page.links[:5])
else:
    print(page.error, "blocked" if page.blocked else "")
```

## How it works

```
fetch(url)
  │
  ├─ cache fresh? ───────────────────────────────────────► page (source: cache)
  │
  ├─ robots.txt for this host (fetched once, kept 24 h)
  │     disallowed? ──────────────────────────────────────► refused, never requested
  │
  ├─ wait for this host's turn: max(min_interval, Crawl-delay) since the last request
  ├─ GET, with If-None-Match / If-Modified-Since when a stale copy is cached
  │     304 ──────────────────────────────────────────────► page (source: revalidated)
  │     301-308 ─► the same checks again for the new URL (5 hops at most)
  │     429, 5xx, network error ─► wait Retry-After, or 1 s, 2 s, 4 s ... then try again
  │     403/503 bot check page ───────────────────────────► blocked, no retry
  │
  └─ HTML ─► title, text (no scripts, styles or SVG), absolute links ─► cache ─► page
```

The rules, worked through by hand: [docs/explained.md](docs/explained.md).

## A worked example

`python examples/demo.py` reads five URLs from a made-up bike shop's site. Its robots.txt
disallows `/private/` and sets `Crawl-delay: 1`, and `/busy` answers the first request with 429
and `Retry-After: 2`:

```
/                    ok       network  tries=1   0.6s  'Kettle Lane Cycles', 172 chars, 3 links
/hours.html          ok       network  tries=1   1.0s  'Opening hours', 113 chars, 1 links
/private/notes.html  refused  -        tries=0   0.0s  disallowed by robots.txt
/busy                ok       network  tries=2   3.0s  'Opening hours', 113 chars, 1 links
/                    ok       cache    tries=0   0.0s  'Kettle Lane Cycles', 172 chars, 3 links

What the server saw (seconds since start):
   0.06  GET /robots.txt
   0.67  GET /
   1.68  GET /hours.html
   2.68  GET /busy
   4.68  GET /busy
```

Five pages asked for, five requests made, one of them robots.txt. The private page was never
requested, the busy page was asked again exactly when the server said, and the second read of the
home page came from the cache. Requests are a second apart because the site asked for that, not
the half second the demo set.

## What I learned

- **A 403 with "Just a moment..." is not the page.** I first met this reading sites for research:
  a bot check page came back with a status and some text, and the code treated that text as the
  site. Now a challenge page is its own outcome, `blocked`, and it is never retried or cached.
- **robots.txt precedence is the longest rule, not the first.** With `Disallow: /` and then
  `Allow: /public/`, `/public/page` is allowed. RFC 9309 settled this in 2022. I match the rules
  myself so the answer is the same on every Python version, and the tests check both orders.
- **Every redirect hop is a new request.** A redirect from an allowed URL to a disallowed one has
  to stop at the redirect. Following redirects by hand is what lets robots.txt and the per-host
  wait apply to each hop.
- **Make time injectable.** The reader takes a clock and a sleep function. The tests pass fake
  ones, so checking "waits 2 s, then 7 s, then 7 s" takes no time and never flakes.

## Limits

- One request at a time per host, and one thread. For thousands of pages per hour, use a real
  crawler (Scrapy) and keep these rules.
- No JavaScript. Pages built in the browser come back thin; those need a headless browser.
- The bot check detection looks for the common markers. A site with its own check page can still
  slip through as content.
- Pages over `max_bytes` (5 MB by default) are cut off. Only text and HTML are read.
- Percent-encoding in robots.txt paths is compared as written, not normalised.

## Files

```
polite_reader/  reader.py  robots.py  cache.py  extract.py  __main__.py
tests/          unittest against a local server and a fake clock
examples/       demo.py, site/ (a made-up shop with a robots.txt)
docs/           explained.md, decisions.md
```

MIT licence. Copyright 2026 Shinabaze Ajiya.
