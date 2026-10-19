"""Fetch web pages the way a good guest would: robots.txt, one request at a time per host, a
cache, retries that listen to the server, and clean text and links out."""
from .extract import extract
from .reader import USER_AGENT, Page, Reader
from .robots import parse as parse_robots

__all__ = ["Reader", "Page", "USER_AGENT", "extract", "parse_robots"]
__version__ = "0.1.0"
