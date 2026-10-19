import os
import shutil
import tempfile
import unittest

from polite_reader import Reader

from .server import FakeClock, Site

PAGE = "<html><head><title>{0}</title></head><body><p>{0}</p><a href='/next'>next</a></body></html>"


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.site = Site()
        self.clock = FakeClock()
        self.tmp = tempfile.mkdtemp()
        self.site.page("/robots.txt", "User-agent: *\nDisallow: /private/\n", **{"Content-Type": "text/plain"})
        self.site.page("/", PAGE.format("Home"))
        self.site.page("/a", PAGE.format("A"))
        self.site.page("/b", PAGE.format("B"))

    def tearDown(self):
        self.site.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reader(self, **kw):
        opts = dict(min_interval=2.0, cache_dir=os.path.join(self.tmp, "cache"), backoff=1.0, max_wait=30,
                    clock=self.clock.time, sleep=self.clock.sleep)
        opts.update(kw)
        return Reader(**opts)

    def url(self, path):
        return self.site.base + path

    def test_a_page_comes_back_as_title_text_and_links(self):
        page = self.reader().fetch(self.url("/"))
        self.assertTrue(page.ok, page.error)
        self.assertEqual((page.status, page.source, page.title, page.text), (200, "network", "Home", "Home\nnext"))
        self.assertEqual(page.links, [self.url("/next")])

    def test_robots_disallow_means_the_page_is_never_requested(self):
        self.site.page("/private/notes", PAGE.format("secret"))
        page = self.reader().fetch(self.url("/private/notes"))
        self.assertFalse(page.ok)
        self.assertIn("disallowed by robots.txt", page.error)
        self.assertEqual(self.site.hits("/private/notes"), 0)
        self.assertEqual(self.site.hits("/robots.txt"), 1)

    def test_requests_to_one_host_are_spaced_out(self):
        r = self.reader()
        for path in ("/", "/a", "/b"):
            self.assertTrue(r.fetch(self.url(path)).ok)
        # robots.txt, then three pages: three waits of min_interval, and robots.txt is fetched once
        self.assertEqual(self.clock.sleeps, [2.0, 2.0, 2.0])
        self.assertEqual(self.site.hits("/robots.txt"), 1)

    def test_a_longer_crawl_delay_wins(self):
        self.site.page("/robots.txt", "User-agent: *\nCrawl-delay: 5\n", **{"Content-Type": "text/plain"})
        r = self.reader()
        r.fetch(self.url("/"))
        r.fetch(self.url("/a"))
        self.assertEqual(self.clock.sleeps, [2.0, 5.0])

    def test_429_with_retry_after_is_waited_out_then_read(self):
        calls = {"n": 0}

        def busy(req):
            calls["n"] += 1
            return (429, {"Retry-After": "7"}, "slow down") if calls["n"] < 3 else (200, {}, PAGE.format("Busy"))

        self.site.routes["/busy"] = busy
        page = self.reader().fetch(self.url("/busy"))
        self.assertTrue(page.ok, page.error)
        self.assertEqual(page.attempts, 3)
        self.assertEqual(self.clock.sleeps, [2.0, 7.0, 7.0])

    def test_a_retry_after_longer_than_max_wait_is_not_waited(self):
        self.site.page("/later", "come back tomorrow", status=503, **{"Retry-After": "3600"})
        page = self.reader().fetch(self.url("/later"))
        self.assertFalse(page.ok)
        self.assertIn("wait 3600s", page.error)
        self.assertEqual(self.site.hits("/later"), 1)
        self.assertNotIn(3600, self.clock.sleeps)

    def test_server_errors_back_off_then_give_up(self):
        self.site.page("/broken", "oops", status=500)
        page = self.reader(retries=3).fetch(self.url("/broken"))
        self.assertFalse(page.ok)
        self.assertEqual((page.attempts, page.error), (4, "HTTP 500 after 4 tries"))
        # Backoff of 1, 2, 4 seconds, but a retry never comes sooner than the 2s per-host gap:
        # after the 1s backoff it waits 1s more for its turn.
        self.assertEqual(self.clock.sleeps, [2.0, 1.0, 1.0, 2.0, 4.0])

    def test_a_404_is_not_retried(self):
        page = self.reader().fetch(self.url("/missing"))
        self.assertEqual((page.ok, page.status, page.attempts, page.error), (False, 404, 1, "HTTP 404"))

    def test_the_cache_answers_while_fresh_then_asks_if_it_changed(self):
        self.site.routes["/menu"] = lambda req: (
            (304, {"ETag": '"v1"'}, "") if req.headers.get("If-None-Match") == '"v1"' else (200, {"ETag": '"v1"'}, PAGE.format("Menu"))
        )
        r = self.reader(max_age=600)
        first = r.fetch(self.url("/menu"))
        second = r.fetch(self.url("/menu"))
        self.assertEqual((first.source, second.source, second.title), ("network", "cache", "Menu"))
        self.assertEqual(self.site.hits("/menu"), 1)
        self.clock.now += 601
        third = r.fetch(self.url("/menu"))
        self.assertEqual((third.ok, third.source, third.status, third.title), (True, "revalidated", 304, "Menu"))
        self.assertEqual(self.site.log[-1][1].get("If-None-Match"), '"v1"')

    def test_a_challenge_page_is_reported_as_blocked_not_as_content(self):
        self.site.page("/guarded", "<title>Just a moment...</title><div id='cf-chl-widget'></div>", status=503)
        page = self.reader().fetch(self.url("/guarded"))
        self.assertTrue(page.blocked)
        self.assertEqual((page.ok, page.text, page.attempts), (False, "", 1))
        self.assertIn("not the page", page.error)

    def test_every_redirect_hop_is_checked_against_robots(self):
        self.site.page("/old", "", status=301, Location="/private/new")
        self.site.page("/private/new", PAGE.format("hidden"))
        page = self.reader().fetch(self.url("/old"))
        self.assertIn("disallowed by robots.txt", page.error)
        self.assertEqual(page.final_url, self.url("/private/new"))
        self.assertEqual(self.site.hits("/private/new"), 0)

    def test_redirects_are_followed(self):
        self.site.page("/old", "", status=302, Location="/a")
        page = self.reader().fetch(self.url("/old"))
        self.assertEqual((page.ok, page.final_url, page.title), (True, self.url("/a"), "A"))

    def test_robots_txt_status_decides_for_the_whole_site(self):
        for status, expect in ((404, True), (403, False), (500, False)):
            with self.subTest(status=status):
                self.site.log.clear()
                self.site.page("/robots.txt", "", status=status)
                page = self.reader(retries=0, cache_dir=None).fetch(self.url("/a"))
                self.assertEqual(page.ok, expect, page.error)
                self.assertEqual(self.site.hits("/a"), 1 if expect else 0)

    def test_only_text_pages_are_read(self):
        self.site.page("/menu.pdf", b"%PDF-1.7", **{"Content-Type": "application/pdf"})
        page = self.reader().fetch(self.url("/menu.pdf"))
        self.assertEqual(page.error, "not a text page (application/pdf)")

    def test_it_says_who_it_is(self):
        self.reader().fetch(self.url("/"))
        agent = self.site.log[-1][1].get("User-Agent")
        self.assertTrue(agent.startswith("polite-web-reader/"))
        self.assertIn("github.com/shinabaze/polite-web-reader", agent)


if __name__ == "__main__":
    unittest.main()
