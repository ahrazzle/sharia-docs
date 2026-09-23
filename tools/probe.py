#!/usr/bin/env python3
"""Minimal CDP probe: connect, navigate to the app, read title."""
import json
import sys

sys.path.insert(0, "tools")
from dom_evidence import CDP
import http.client

conn = http.client.HTTPConnection("127.0.0.1", 19323, timeout=5)
conn.request("GET", "/json/list")
targets = json.loads(conn.getresponse().read().decode())
page = next(t for t in targets if t.get("type") == "page")
print("page:", page["url"])
cdp = CDP(page["webSocketDebuggerUrl"])
cdp.sock.settimeout(15)
print("title:", cdp.evaluate("document.title"))
cdp.call("Page.enable")
cdp.call("Page.navigate", {"url": "file:///tmp/probe.txt"})
print("navigated ok")
