"""robots.txt, read the way RFC 9309 says.

The longest matching rule wins, and Allow wins a tie. `*` matches any characters and `$` anchors
the end. The rules are matched against the path and the query, and /robots.txt itself is always
allowed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


@dataclass
class Rules:
    """What one site's robots.txt says to one crawler."""

    rules: list[tuple[bool, str]] = field(default_factory=list)
    crawl_delay: float | None = None
    everything: bool | None = None  # True: allow all, False: refuse all, None: use the rules
    why: str = ""

    def allows(self, url: str) -> bool:
        if self.everything is not None:
            return self.everything
        parts = urlsplit(url)
        path = parts.path or "/"
        if path == "/robots.txt":
            return True
        target = path + ("?" + parts.query if parts.query else "")
        best = (-1, True)
        for allow, pattern in self.rules:
            if _compile(pattern).match(target):
                best = max(best, (len(pattern), allow))
        return best[1]


def parse(text: str, product: str) -> Rules:
    """The rules for `product` (the crawler's name, like "polite-web-reader") from a robots.txt."""
    groups: list[Group] = []
    current: Group | None = None
    in_rules = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            # A user-agent line after rules starts a new group; consecutive ones share a group.
            if current is None or in_rules:
                current = Group()
                groups.append(current)
                in_rules = False
            current.agents.append(value.lower())
        elif key in ("allow", "disallow") and current is not None:
            in_rules = True
            if value:  # "Disallow:" with nothing after it disallows nothing
                current.rules.append((key == "allow", value))
        elif key == "crawl-delay" and current is not None:
            in_rules = True
            try:
                current.crawl_delay = float(value)
            except ValueError:
                pass

    product = product.lower()
    mine = [g for g in groups if product in g.agents]
    chosen = mine or [g for g in groups if "*" in g.agents]
    rules = [r for g in chosen for r in g.rules]
    delays = [g.crawl_delay for g in chosen if g.crawl_delay is not None]
    return Rules(rules=rules, crawl_delay=max(delays) if delays else None)


def allow_all(why: str) -> Rules:
    return Rules(everything=True, why=why)


def refuse_all(why: str) -> Rules:
    return Rules(everything=False, why=why)


_cache: dict[str, re.Pattern] = {}


def _compile(pattern: str) -> re.Pattern:
    if pattern not in _cache:
        anchored = pattern.endswith("$")
        body = re.escape(pattern[:-1] if anchored else pattern).replace(r"\*", ".*")
        _cache[pattern] = re.compile(body + ("$" if anchored else ""))
    return _cache[pattern]
