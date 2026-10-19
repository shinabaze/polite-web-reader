"""python -m polite_reader URL [URL ...] [--json] [--links] [--interval 1] [--max-age 3600] [--no-cache]"""
import argparse
import json
import sys

from .reader import Reader


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m polite_reader", description="Fetch pages politely and print their text.")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--json", action="store_true", help="print each page as JSON")
    ap.add_argument("--links", action="store_true", help="print the links instead of the text")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between requests to one host (default 1)")
    ap.add_argument("--max-age", type=float, default=3600, help="seconds a cached page stays fresh (default 3600)")
    ap.add_argument("--cache-dir", default=".cache/polite-reader")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--max", type=int, default=4000, help="characters of text to print per page")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    reader = Reader(min_interval=a.interval, max_age=a.max_age, cache_dir=None if a.no_cache else a.cache_dir)
    failed = 0
    for url in a.urls:
        page = reader.fetch(url)
        failed += not page.ok
        if a.json:
            print(json.dumps(page.to_dict(), ensure_ascii=False))
            continue
        head = f"{page.status or '-'} {page.source or '-':<11} {page.final_url}"
        if not page.ok:
            print(f"{head}\n  {page.error}\n")
        elif a.links:
            print(head + "".join(f"\n  {link}" for link in page.links) + "\n")
        else:
            print(f"{head}\n# {page.title}\n{page.text[:a.max]}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
