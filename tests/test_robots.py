import unittest

from polite_reader.robots import parse

URL = "https://shop.example"


def allows(text, path, product="polite-web-reader"):
    return parse(text, product).allows(URL + path)


class Robots(unittest.TestCase):
    def test_longest_match_wins_whatever_the_order(self):
        for text in ("User-agent: *\nDisallow: /\nAllow: /public/\n", "User-agent: *\nAllow: /public/\nDisallow: /\n"):
            self.assertTrue(allows(text, "/public/page"), text)
            self.assertFalse(allows(text, "/cart"), text)

    def test_allow_wins_a_tie(self):
        text = "User-agent: *\nDisallow: /page\nAllow: /page\n"
        self.assertTrue(allows(text, "/page"))

    def test_wildcards_and_end_anchor(self):
        text = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /search?\n"
        self.assertFalse(allows(text, "/files/menu.pdf"))
        self.assertTrue(allows(text, "/files/menu.pdf?download=1"))
        self.assertTrue(allows(text, "/files/menu.pdfx"))
        self.assertFalse(allows(text, "/search?q=bikes"))
        self.assertTrue(allows(text, "/search"))

    def test_rules_are_prefixes(self):
        text = "User-agent: *\nDisallow: /private\n"
        self.assertFalse(allows(text, "/private"))
        self.assertFalse(allows(text, "/private-notes"))
        self.assertTrue(allows(text, "/public/private"))

    def test_our_own_group_replaces_the_star_group(self):
        text = ("User-agent: *\nDisallow: /\n\n"
                "User-agent: Polite-Web-Reader\nDisallow: /admin\nCrawl-delay: 5\n")
        rules = parse(text, "polite-web-reader")
        self.assertTrue(rules.allows(URL + "/menu"))
        self.assertFalse(rules.allows(URL + "/admin"))
        self.assertEqual(rules.crawl_delay, 5)
        self.assertFalse(allows(text, "/menu", product="other-bot"))

    def test_consecutive_user_agent_lines_share_a_group(self):
        text = "User-agent: a-bot\nUser-agent: polite-web-reader\nDisallow: /x\n\nUser-agent: *\nDisallow: /\n"
        self.assertFalse(allows(text, "/x"))
        self.assertTrue(allows(text, "/y"))

    def test_empty_disallow_comments_and_junk(self):
        text = "# hello\nUser-agent: * # everyone\nDisallow:\nnonsense line\nSitemap: https://shop.example/sitemap.xml\n"
        self.assertTrue(allows(text, "/anything"))

    def test_robots_txt_itself_is_always_allowed(self):
        self.assertTrue(allows("User-agent: *\nDisallow: /\n", "/robots.txt"))


if __name__ == "__main__":
    unittest.main()
