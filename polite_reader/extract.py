"""HTML in, the title, the readable text and the links out. Standard library only."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

SKIP = {"script", "style", "noscript", "template", "svg", "iframe"}
BLOCK = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption",
    "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
    "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
}


class _Extractor(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self.parts: list[str] = []
        self.links: dict[str, None] = {}
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "base" and a.get("href"):
            self.base = urljoin(self.base, a["href"])
        elif tag == "a" and a.get("href"):
            link = urldefrag(urljoin(self.base, a["href"].strip())).url
            if urlsplit(link).scheme in ("http", "https"):
                self.links.setdefault(link)
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        else:
            self.parts.append(data)


def extract(html: str, url: str) -> dict:
    """{"title", "text", "links"} for a page fetched from `url` (links are absolute, no fragments)."""
    p = _Extractor(url)
    p.feed(html)
    p.close()
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(p.parts).split("\n"))
    text = "\n".join(line for line in lines if line)
    return {"title": re.sub(r"\s+", " ", p.title).strip(), "text": text, "links": list(p.links)}


def decode(body: bytes, content_type: str) -> str:
    """Bytes to text: the charset from the header, else from a <meta> tag, else UTF-8."""
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    charset = m.group(1) if m else None
    if not charset:
        meta = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
        charset = meta.group(1).decode("ascii") if meta else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")
