"""The reader: robots.txt first, one request at a time per host, a cache, and retries that listen."""
from __future__ import annotations

import email.utils
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlsplit

from . import robots
from .cache import DiskCache
from .extract import decode, extract

USER_AGENT = "polite-web-reader/0.1 (+https://github.com/shinabaze/polite-web-reader)"
RETRY = {429, 500, 502, 503, 504}
REDIRECT = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
ROBOTS_TTL = 24 * 3600
# Text that bot-protection pages show instead of the site. Seen with a 403 or 503, it means "you
# were stopped at the door", which is a different answer from "the page is broken".
CHALLENGE = ("just a moment...", "cf-chl-", "challenge-platform", "attention required!",
             "enable javascript and cookies to continue", "verify you are human", "captcha")


@dataclass
class Page:
    url: str
    ok: bool = False
    status: int = 0
    final_url: str = ""
    source: str = "network"  # network, cache, or revalidated (the server said "not modified")
    content_type: str = ""
    title: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    error: str = ""
    blocked: bool = False
    attempts: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Redirects are followed by hand so robots.txt and the rate limit apply to every hop.
    def redirect_request(self, *args, **kwargs):
        return None


def retry_after(headers: dict, now: float) -> float | None:
    """Seconds to wait from a Retry-After header: a number, or an HTTP date."""
    value = headers.get("retry-after", "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, email.utils.parsedate_to_datetime(value).timestamp() - now)
    except (TypeError, ValueError):
        return None


def looks_blocked(status: int, headers: dict, body: bytes) -> bool:
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if status not in (403, 503):
        return False
    head = body[:20000].decode("utf-8", errors="replace").lower()
    return any(marker in head for marker in CHALLENGE)


class Reader:
    """Reads pages politely. One instance per crawl, so the per-host clocks are shared.

    min_interval  seconds between two requests to the same host (a larger Crawl-delay wins)
    cache_dir     where to keep pages; None turns the cache off
    max_age       seconds a cached page counts as fresh; after that it is checked with the server
    retries       extra tries after a 429, a 5xx or a network error
    backoff       first wait between tries, doubled each time, when the server gives no Retry-After
    max_wait      the longest single wait it will do; a server asking for more gets no retry
    """

    def __init__(self, user_agent: str = USER_AGENT, min_interval: float = 1.0, cache_dir: str | None = ".cache/polite-reader",
                 max_age: float = 3600, retries: int = 3, backoff: float = 1.0, max_wait: float = 60.0,
                 timeout: float = 20.0, max_bytes: int = 5_000_000, clock=time.time, sleep=time.sleep):
        self.user_agent = user_agent
        self.product = user_agent.split("/")[0].strip()
        self.min_interval = min_interval
        self.cache = DiskCache(cache_dir) if cache_dir else None
        self.max_age = max_age
        self.retries = retries
        self.backoff = backoff
        self.max_wait = max_wait
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.clock = clock
        self.sleep = sleep
        self._next: dict[str, float] = {}
        self._robots: dict[str, tuple[robots.Rules, float]] = {}
        self._opener = urllib.request.build_opener(_NoRedirect)

    # ---------------------------------------------------------------- one HTTP request
    def _open(self, url: str, headers: dict) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5", **headers})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                status, hdrs, body = r.status, r.headers, r.read(self.max_bytes)
        except urllib.error.HTTPError as e:
            status, hdrs, body = e.code, e.headers, e.read(self.max_bytes)
        return status, {k.lower(): v for k, v in hdrs.items()}, body

    def _wait_turn(self, host: str) -> None:
        wait = self._next.get(host, 0.0) - self.clock()
        if wait > 0:
            self.sleep(wait)

    def _request(self, url: str, headers: dict, interval: float) -> tuple[int, dict, bytes, int, str]:
        """One URL with retries. Returns (status, headers, body, attempts, error)."""
        host = urlsplit(url).netloc
        status, hdrs, body, error = 0, {}, b"", ""
        for attempt in range(self.retries + 1):
            self._wait_turn(host)
            try:
                status, hdrs, body = self._open(url, headers)
                error = ""
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
                status, hdrs, body = 0, {}, b""
                error = f"network error: {getattr(e, 'reason', e)}"
            finally:
                self._next[host] = self.clock() + interval
            if status and (status not in RETRY or looks_blocked(status, hdrs, body)):
                return status, hdrs, body, attempt + 1, ""
            if attempt == self.retries:
                break
            wait = retry_after(hdrs, self.clock())
            if wait is None:
                wait = self.backoff * 2 ** attempt
            if wait > self.max_wait:
                return status, hdrs, body, attempt + 1, f"the server asked us to wait {wait:.0f}s, more than max_wait ({self.max_wait:.0f}s)"
            self.sleep(wait)
        return status, hdrs, body, self.retries + 1, error or f"HTTP {status} after {self.retries + 1} tries"

    # ---------------------------------------------------------------- robots.txt
    def rules_for(self, url: str) -> robots.Rules:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        hit = self._robots.get(origin)
        if hit and self.clock() - hit[1] < ROBOTS_TTL:
            return hit[0]
        target, status, body, error = f"{origin}/robots.txt", 0, b"", ""
        for _ in range(MAX_REDIRECTS + 1):
            status, hdrs, body, _, error = self._request(target, {}, self.min_interval)
            if status in REDIRECT and hdrs.get("location"):
                target = urljoin(target, hdrs["location"])
                continue
            break
        if 200 <= status < 300:
            rules = robots.parse(decode(body, hdrs.get("content-type", "")), self.product)
        elif status in (401, 403):
            rules = robots.refuse_all(f"robots.txt answered {status}")
        elif 400 <= status < 500:
            rules = robots.allow_all(f"no robots.txt ({status})")
        else:
            rules = robots.refuse_all(f"robots.txt unreachable ({error or status})")
        self._robots[origin] = (rules, self.clock())
        return rules

    # ---------------------------------------------------------------- the page
    def fetch(self, url: str) -> Page:
        page = Page(url=url, final_url=url)
        if urlsplit(url).scheme not in ("http", "https"):
            page.error = "only http and https URLs"
            return page

        cached = self.cache.get(url) if self.cache else None
        if cached and self.clock() - cached["fetched_at"] < self.max_age:
            return self._from_entry(page, cached, "cache")

        current, status, hdrs, body = url, 0, {}, b""
        for _ in range(MAX_REDIRECTS + 1):
            rules = self.rules_for(current)
            if not rules.allows(current):
                page.final_url = current
                page.error = f"disallowed by robots.txt{': ' + rules.why if rules.why else ''}"
                return page
            headers = {}
            if cached and current == url:
                if cached.get("etag"):
                    headers["If-None-Match"] = cached["etag"]
                if cached.get("last_modified"):
                    headers["If-Modified-Since"] = cached["last_modified"]
            interval = max(self.min_interval, rules.crawl_delay or 0)
            status, hdrs, body, attempts, error = self._request(current, headers, interval)
            page.attempts += attempts
            if status in REDIRECT and hdrs.get("location"):
                current = urljoin(current, hdrs["location"])
                continue
            break
        else:
            page.error = f"more than {MAX_REDIRECTS} redirects"
            return page

        page.status, page.final_url = status, current
        if status == 304 and cached:
            cached["fetched_at"] = self.clock()
            self.cache.put(url, cached)
            return self._from_entry(page, cached, "revalidated")
        if looks_blocked(status, hdrs, body):
            page.blocked = True
            page.error = f"stopped by a bot check (HTTP {status}); this is not the page"
            return page
        if error or not 200 <= status < 300:
            page.error = error or f"HTTP {status}"
            return page

        page.content_type = hdrs.get("content-type", "").split(";")[0].strip().lower()
        if page.content_type not in ("text/html", "application/xhtml+xml", "text/plain", ""):
            page.error = f"not a text page ({page.content_type})"
            return page
        entry = {"final_url": current, "status": status, "content_type": page.content_type,
                 "etag": hdrs.get("etag", ""), "last_modified": hdrs.get("last-modified", ""),
                 "fetched_at": self.clock(), "body": decode(body, hdrs.get("content-type", ""))}
        if self.cache:
            self.cache.put(url, entry)
        return self._from_entry(page, entry, "network")

    def _from_entry(self, page: Page, entry: dict, source: str) -> Page:
        page.ok, page.source = True, source
        page.status = page.status or entry["status"]
        page.final_url = entry["final_url"]
        page.content_type = entry["content_type"]
        if page.content_type == "text/plain":
            page.text = entry["body"].strip()
        else:
            got = extract(entry["body"], entry["final_url"])
            page.title, page.text, page.links = got["title"], got["text"], got["links"]
        return page
