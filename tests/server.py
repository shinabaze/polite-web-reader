"""A local web server for the tests. Each route is a function returning (status, headers, body)."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Site:
    def __init__(self):
        self.routes = {}
        self.log = []  # (path, request headers) for every request, in order
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.log.append((self.path, dict(self.headers)))
                route = site.routes.get(self.path)
                status, headers, body = route(self) if route else (404, {}, "not here")
                data = body.encode() if isinstance(body, str) else body
                self.send_response(status)
                headers = {"Content-Type": "text/html; charset=utf-8", **headers}
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def page(self, path, body, status=200, **headers):
        self.routes[path] = lambda req: (status, headers, body)

    def hits(self, path):
        return sum(1 for p, _ in self.log if p == path)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeClock:
    """Stands in for time.time and time.sleep: sleeping moves the clock, and every sleep is kept."""

    def __init__(self, start=1_000_000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds
