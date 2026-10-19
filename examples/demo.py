"""Run the reader against a small local site, with the real clock, and print what happened.

    python examples/demo.py

The site is examples/site, served on 127.0.0.1. Its robots.txt disallows /private/ and asks for
one second between requests. /busy is a route that answers 429 "come back in 2 seconds" the first
time it is asked. Nothing leaves your machine.
"""
import os
import shutil
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from polite_reader import Reader  # noqa: E402

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
requests = []


class Handler(SimpleHTTPRequestHandler):
    busy_once = True

    def do_GET(self):
        requests.append((round(time.perf_counter() - START, 2), self.path))
        if self.path == "/busy":
            if Handler.busy_once:
                Handler.busy_once = False
                self.send_response(429)
                self.send_header("Retry-After", "2")
                self.end_headers()
                return
            self.path = "/hours.html"
        super().do_GET()

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=SITE))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    cache = tempfile.mkdtemp()
    reader = Reader(min_interval=0.5, cache_dir=cache)
    try:
        for path in ("/", "/hours.html", "/private/notes.html", "/busy", "/"):
            t = time.perf_counter()
            page = reader.fetch(base + path)
            took = time.perf_counter() - t
            what = f"{page.title!r}, {len(page.text)} chars, {len(page.links)} links" if page.ok else page.error
            print(f"{path:<20} {('ok' if page.ok else 'refused'):<8} {page.source or '-':<8} tries={page.attempts}  {took:4.1f}s  {what}")
        print("\nWhat the server saw (seconds since start):")
        for at, path in requests:
            print(f"  {at:5.2f}  GET {path}")
    finally:
        server.shutdown()
        shutil.rmtree(cache, ignore_errors=True)


START = time.perf_counter()
if __name__ == "__main__":
    main()
