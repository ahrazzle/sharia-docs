#!/usr/bin/env python3
"""SCW headless DOM evidence. Stdlib only.

Launches Playwright-cached Chromium headless, drives app/index.html over
CDP (minimal stdlib websocket client): asserts title/chips/pack identity,
proves the no-term guided flow (zero default terms, refusal gate),
pastes the golden free-text vector, clicks Run, proves the standing
in-app label, reads back the four panes, captures a screenshot.
Writes evidence/dom-evidence.json + evidence/dom.png.

Usage: python3 tools/dom_evidence.py  (from the repo root)
"""
import base64
import hashlib
import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.parse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "app", "index.html")
EVDIR = os.path.join(BASE, "evidence")
CHROME = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/"
    "Google Chrome for Testing")
PORT = 19322
GOLDEN_TEXT = ("This term sheet proposes a murabaha facility for equipment "
               "purchase with the profit margin disclosed at signing. "
               "A parallel ijara covers the same assets. The client also "
               "asked about مرابحة pricing and whether the fund's takaful "
               "wrapper is acceptable. Interest on the bridging loan is 5 "
               "percent. The desk also wants exposure to crypto futures.")


class CDP:
    def __init__(self, ws_url):
        p = urllib.parse.urlparse(ws_url)
        self.sock = socket.create_connection((p.hostname, p.port or 80))
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: %s:%s\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n"
               % (p.path, p.hostname, p.port, key))
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.sock.recv(4096)
        assert b"101" in head.split(b"\r\n")[0], head[:80]
        self.sock.settimeout(30)
        self.seq = 0
        self.buf = b""

    def _send(self, text):
        data = text.encode()
        hdr = bytes([0x81, 0x80 | len(data)]) if len(data) < 126 else struct.pack(
            "!BBH", 0x81, 0x80 | 126, len(data))
        mask = os.urandom(4)
        self.sock.sendall(hdr + mask + bytes(
            b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv_frame(self):
        while len(self.buf) < 2:
            self.buf += self.sock.recv(65536)
        b1, b2 = self.buf[0], self.buf[1]
        n = b2 & 0x7F
        idx = 2
        if n == 126:
            while len(self.buf) < 4:
                self.buf += self.sock.recv(65536)
            n = struct.unpack("!H", self.buf[2:4])[0]
            idx = 4
        elif n == 127:
            while len(self.buf) < 10:
                self.buf += self.sock.recv(65536)
            n = struct.unpack("!Q", self.buf[2:10])[0]
            idx = 10
        while len(self.buf) < idx + n:
            self.buf += self.sock.recv(65536)
        payload = self.buf[idx:idx + n]
        self.buf = self.buf[idx + n:]
        return b1 & 0x0F, payload

    def _ping(self):
        self.sock.sendall(bytes([0x89, 0x80]) + os.urandom(4))

    def call(self, method, params=None, timeout=20):
        self.seq += 1
        self._send(json.dumps(
            {"id": self.seq, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            op, payload = self._recv_frame()
            if op == 0x8:
                raise RuntimeError("ws closed")
            if op != 0x1:
                continue
            msg = json.loads(payload.decode())
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})
        raise RuntimeError("cdp timeout on " + method)

    def evaluate(self, expr, timeout=20):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True,
                       "awaitPromise": True}, timeout)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")


def main():
    os.makedirs(EVDIR, exist_ok=True)
    profile = os.path.join(EVDIR, ".chrome-profile")
    proc = subprocess.Popen(
        [CHROME, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", "--user-data-dir=" + profile,
         "--remote-debugging-port=%d" % PORT, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        target = None
        for _ in range(100):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", PORT,
                                                  timeout=2)
                conn.request("GET", "/json/list")
                targets = json.loads(conn.getresponse().read().decode())
                target = next(t for t in targets
                              if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.2)
        assert target, "no debuggable page"
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call("Page.navigate",
                 {"url": "file://" + urllib.parse.quote(APP)})
        for _ in range(100):
            time.sleep(0.2)
            try:
                if cdp.evaluate("document.readyState") == "complete" \
                        and cdp.evaluate(
                            "!!(window.PACK && window.scwEvaluate)"):
                    break
            except RuntimeError:
                pass
        ev = {}
        ev["title"] = cdp.evaluate("document.title")
        ev["pack_ok"] = cdp.evaluate("PACK_OK")
        ev["pack_sha_live"] = cdp.evaluate("packShaLive")
        ev["chips"] = cdp.evaluate(
            "document.getElementById('chips').innerText")
        ev["rail"] = cdp.evaluate(
            "Array.from(document.querySelectorAll('#rail button'))"
            ".map(function(b){return b.textContent;})")
        ev["golden_text_len"] = cdp.evaluate(
            "document.getElementById('freetext').value.length")
        # Guided refusal-gate probes: fresh load,
        # enter Guided, Item 1 must carry zero checked terms; running in
        # that state must refuse with exact copy, never substitute.
        cdp.evaluate("document.getElementById('m-guided').click()")
        ev["guided_item_count"] = cdp.evaluate("guidedItems.length")
        ev["guided_checked_count"] = cdp.evaluate(
            "document.querySelectorAll('#gform input[data-t]:checked').length")
        ev["guided_helper_en"] = cdp.evaluate(
            "document.body.textContent.indexOf('Select at least one "
            "structure term') !== -1")
        cdp.evaluate("document.getElementById('run').click()")
        time.sleep(0.3)
        ev["guided_refusal_result_null"] = cdp.evaluate("STATE.result === null")
        ev["guided_refusal_warn"] = cdp.evaluate(
            "document.getElementById('runwarn').textContent")
        ev["guided_refusal_warn_role"] = cdp.evaluate(
            "document.getElementById('runwarn').getAttribute('role')")
        ev["guided_refusal_exp_disabled"] = cdp.evaluate(
            "document.getElementById('exp-json').disabled === true")
        ev["guided_refusal_pane"] = cdp.evaluate(
            "document.querySelector('.pane.on').id")
        # back to paste mode for the golden free-text vector
        cdp.evaluate("document.getElementById('m-paste').click()")
        # drive the golden free-text vector end to end
        cdp.evaluate(
            "document.getElementById('freetext').value = %s;"
            "updateCounter();doRun();" % json.dumps(GOLDEN_TEXT))
        time.sleep(0.5)
        ev["structure_visible"] = cdp.evaluate(
            "document.getElementById('pane-structure')"
            ".classList.contains('on')")
        ev["structure_items"] = cdp.evaluate(
            "document.querySelectorAll('#p1list div').length")
        ev["structure_meter"] = cdp.evaluate(
            "document.getElementById('p1meter').textContent")
        # In-app standing label: two
        # data-statuslabel instances, printable, both sentences.
        ev["status_label_count"] = cdp.evaluate(
            "document.querySelectorAll('[data-statuslabel]').length")
        ev["status_label_visible"] = cdp.evaluate(
            "document.getElementById('statuslabel').hidden === false")
        ev["status_label_printable"] = cdp.evaluate(
            "document.getElementById('statuslabel')"
            ".closest('.noprint') === null")
        ev["status_label_text"] = cdp.evaluate(
            "document.getElementById('statuslabel').textContent")
        cdp.evaluate("show('pane-worksheet')")
        ev["worksheet_rows"] = cdp.evaluate(
            "document.querySelectorAll('#p2tb tr').length")
        ev["worksheet_head"] = cdp.evaluate(
            "document.getElementById('p2head').innerText")
        cdp.evaluate("show('pane-attestation')")
        ev["attestation_run"] = cdp.evaluate(
            "document.getElementById('p3body').innerText.slice(0, 400)")
        ev["limits_count"] = cdp.evaluate(
            "document.querySelectorAll('#limits li').length")
        ev["signoff_text"] = cdp.evaluate(
            "document.getElementById('signoff').innerText.slice(0, 200)")
        cdp.evaluate("show('pane-unverified')")
        ev["unverified_rows"] = cdp.evaluate(
            "document.querySelectorAll('#p4tb tr').length")
        # confirm one reading, prove the meter moves (UI-session only)
        cdp.evaluate("show('pane-structure')")
        before = cdp.evaluate(
            "document.getElementById('p1meter').textContent")
        clicked = cdp.evaluate(
            "(function(){var b=document.querySelector('#p1list "
            "button[data-c]');if(b){b.click();return true;}return false;})()")
        after = cdp.evaluate(
            "document.getElementById('p1meter').textContent")
        ev["confirm_flow"] = {"clicked": clicked, "before": before,
                              "after": after}
        shot = cdp.call("Page.captureScreenshot", {"format": "png"})
        with open(os.path.join(EVDIR, "dom.png"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        with open(os.path.join(EVDIR, "dom-evidence.json"), "w",
                  encoding="utf-8") as f:
            json.dump(ev, f, ensure_ascii=False, indent=2,
                      sort_keys=True)
        print(json.dumps(ev, ensure_ascii=False, indent=2,
                         sort_keys=True))
        checks = [
            ("title", ev["title"] == "Sharia-Compliance Workbook"),
            ("pack_ok", ev["pack_ok"] is True),
            ("pack_sha",
             ev["pack_sha_live"] == "1ea71e863f05f7b8c1c2fd64ce0b58fd03de5a3512e25b15d4bee64451cae042"),
            ("guided_zero_default",
             ev["guided_item_count"] == 1 and ev["guided_checked_count"] == 0
             and ev["guided_helper_en"] is True),
            ("guided_refusal_gate",
             ev["guided_refusal_result_null"] is True
             and "Item 1: no structure term selected" in ev["guided_refusal_warn"]
             and "The workbook will not choose one for you." in ev["guided_refusal_warn"]
             and ev["guided_refusal_warn_role"] == "alert"
             and ev["guided_refusal_exp_disabled"] is True
             and ev["guided_refusal_pane"] == "pane-intake"),
            ("status_label",
             ev["status_label_count"] == 2
             and ev["status_label_visible"] is True
             and ev["status_label_printable"] is True
             and "Input status: unconfirmed input" in ev["status_label_text"]
             and "مدخلات غير مؤكدة" in ev["status_label_text"]),
            ("structure_items", ev["structure_items"] == 3),
            ("worksheet_rows", ev["worksheet_rows"] >= 4),
            ("limits_8", ev["limits_count"] == 8),
            ("unverified_12", ev["unverified_rows"] == 12),
            ("confirm_moves", before != after),
        ]
        bad = [k for k, ok in checks if not ok]
        print("DOM CHECKS: %d/%d pass" % (len(checks) - len(bad),
                                          len(checks)))
        if bad:
            print("FAILED: " + ", ".join(bad))
        return 1 if bad else 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
