# Decisions

**Standard library only.** `requests` and `httpx` are nicer, but a reader that is copied into a
script or a scheduled job should not need anything installed. `urllib` does everything needed here
once redirects are handled by hand.

**Its own robots.txt matcher.** `urllib.robotparser` fetches robots.txt itself with a bare
`urlopen`, so the user agent, the per-host turn and the retries would not apply to that request.
The matcher here is under 100 lines, follows RFC 9309, and is tested against the cases in
[explained.md](explained.md) on Python 3.10 and 3.13 in CI, so the answer doesn't depend on which
Python runs it.

**Redirects by hand.** `urllib` follows redirects silently, which skips robots.txt and the wait for
every hop after the first. The reader turns that off and follows up to five hops itself.

**A bot check is "blocked", never content.** A 403 or 503 page saying "Just a moment..." or
asking for a captcha is the site's front door, not the page. Returning its text as content is
how a summariser ends up describing a bot check. It is also not retried: asking again faster
only makes it worse.

**Give up on long Retry-After.** A server that says "come back in an hour" is answered by not
retrying, with an error that says so. A caller that really wants to wait can raise `max_wait`.

**No jitter in the backoff.** Random jitter spreads out many clients hitting one server at once.
One reader on one machine doesn't need it, and leaving it out keeps the waits exact and testable.

**One file per cached page, written by rename.** The cache is a folder of JSON files named by the
SHA-256 of the URL. Each one is written to a temporary file and renamed into place, so a crash
can't leave a half-written entry that is read as a page later.

**The clock is a parameter.** `Reader(clock=..., sleep=...)` defaults to `time.time` and
`time.sleep`. The tests pass a fake clock, which makes every wait exact and the whole suite run
in seconds.
