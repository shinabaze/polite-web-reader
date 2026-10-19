# The rules, worked by hand

## robots.txt: which rule applies

A robots.txt is a list of groups. Each group starts with one or more `User-agent` lines and is
followed by `Allow` and `Disallow` rules:

```
User-agent: *
Disallow: /
Allow: /public/

User-agent: polite-web-reader
Disallow: /admin
Crawl-delay: 5
```

**Pick the group.** The reader's name is the part of its user agent before the slash,
`polite-web-reader`. If a group names it (in any case), that group applies and `*` is ignored.
Here that means only `Disallow: /admin` and `Crawl-delay: 5` apply. A crawler called `other-bot`
gets the `*` group.

**Pick the rule.** Every rule whose pattern matches the start of the path (plus the query) is a
candidate, and the longest pattern wins. Take the `*` group and the path `/public/menu`:

| Rule | Matches? | Length |
|---|---|---|
| `Disallow: /` | yes | 1 |
| `Allow: /public/` | yes | 8 |

`Allow: /public/` is longer, so the page is allowed, whichever line comes first in the file. If two
matching rules are the same length, `Allow` wins. If nothing matches, the page is allowed.

**Patterns.** `*` matches any run of characters and `$` at the end means "and nothing after":

| Rule | `/files/menu.pdf` | `/files/menu.pdf?dl=1` | `/files/menu.pdfx` |
|---|---|---|---|
| `Disallow: /*.pdf$` | disallowed | allowed | allowed |
| `Disallow: /*.pdf` | disallowed | disallowed | disallowed |

Rules are prefixes: `Disallow: /private` also covers `/private-notes`. `/robots.txt` itself is
always allowed.

## robots.txt: when there isn't one

| The server answers /robots.txt with | The reader |
|---|---|
| 200 | follows the rules |
| 404 or another 4xx | reads anything: there are no rules |
| 401 or 403 | reads nothing: the site is refusing robots at the door |
| 5xx, or no answer | reads nothing for now: the site can't say what it wants |

RFC 9309 allows reading anything after a 401 or 403. I treat those as "no", which is stricter
than the standard and what Python's own `robotparser` does too.

## Taking turns

Each host has a "next allowed" time. Before a request, the reader sleeps until then; after it,
the next allowed time is now plus the gap. The gap is `min_interval`, or the site's
`Crawl-delay` if that is longer.

With `min_interval=2` and three pages on one host, starting at t=0:

| t | Request | Next allowed |
|---|---|---|
| 0 | robots.txt | 2 |
| 2 (slept 2) | page 1 | 4 |
| 4 (slept 2) | page 2 | 6 |
| 6 (slept 2) | page 3 | 8 |

robots.txt is a request like any other, so it takes a turn too.

## Retries

A 429, a 500, 502, 503 or 504, or a network error gets another try, up to `retries` times.

- If the answer has `Retry-After`, the reader waits that long. It can be seconds (`7`) or a date
  (`Wed, 21 Oct 2026 07:28:00 GMT`).
- If not, it waits `backoff`, then twice that, then four times: 1 s, 2 s, 4 s.
- If the server asks for longer than `max_wait`, the reader gives up at once rather than sit
  there for an hour. The error says how long it was asked to wait.

The per-host turn still applies on top. With a 2 s gap and a 1 s backoff, the first retry sleeps
1 s for the backoff and then 1 s more for its turn.

A 404 or any other 4xx is not retried: asking again gets the same answer.

## The cache

A page is stored with when it was fetched and the server's validators (`ETag`,
`Last-Modified`).

- Younger than `max_age`: returned straight from disk, no request.
- Older: requested again with `If-None-Match` and `If-Modified-Since`. A `304 Not Modified`
  answer has no body; the reader marks its copy fresh again and returns it as `revalidated`.
  A `200` replaces the copy.

A revalidation still costs a request, but a 304 is a few hundred bytes instead of the whole page.
