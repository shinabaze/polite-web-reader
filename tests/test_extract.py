import unittest

from polite_reader.extract import decode, extract

HTML = """<!doctype html><html><head><title> Opening
  hours </title><style>p { color: red }</style><script>var hidden = "no"</script></head>
<body><nav><a href="/">Home</a> <a href="/menu#lunch">Menu</a></nav>
<main><h1>Hours</h1><p>Open 9&nbsp;to&nbsp;5, Tuesday&ndash;Sunday.</p>
<p>Closed on <b>Mondays</b>.</p><svg><text>chart label</text></svg>
<a href="https://maps.example/shop">Map</a> <a href="mailto:hi@shop.example">Mail</a> <a href="/menu">Menu again</a>
</main></body></html>"""


class Extract(unittest.TestCase):
    def test_title_text_and_links(self):
        got = extract(HTML, "https://shop.example/hours/")
        self.assertEqual(got["title"], "Opening hours")
        self.assertEqual(got["text"], "Home Menu\nHours\nOpen 9 to 5, Tuesday–Sunday.\nClosed on Mondays.\nMap Mail Menu again")
        self.assertEqual(got["links"], ["https://shop.example/", "https://shop.example/menu", "https://maps.example/shop"])

    def test_scripts_styles_and_svg_text_are_dropped(self):
        text = extract(HTML, "https://shop.example/")["text"]
        for gone in ("hidden", "color: red", "chart label"):
            self.assertNotIn(gone, text)

    def test_base_href_changes_where_links_point(self):
        got = extract('<base href="https://cdn.example/docs/"><a href="guide.html">g</a>', "https://shop.example/")
        self.assertEqual(got["links"], ["https://cdn.example/docs/guide.html"])

    def test_charset_from_header_then_meta_then_utf8(self):
        body = "café".encode("latin-1")
        self.assertEqual(decode(body, "text/html; charset=ISO-8859-1"), "café")
        self.assertEqual(decode(b'<meta charset="iso-8859-1">' + body, "text/html"), '<meta charset="iso-8859-1">café')
        self.assertEqual(decode("café".encode(), "text/html"), "café")
        self.assertEqual(decode("café".encode(), "text/html; charset=nonsense"), "café")


if __name__ == "__main__":
    unittest.main()
