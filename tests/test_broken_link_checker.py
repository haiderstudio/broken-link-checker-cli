#!/usr/bin/env python3
"""Tests for broken_link_checker. Run: python3 tests/test_broken_link_checker.py

No third-party dependencies. Remote checks run against a real local
HTTP server started by the tests, never against the public internet.
"""

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from broken_link_checker import (  # noqa: E402
    check_files,
    check_link,
    extract_links,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "broken_link_checker.py"


class FixtureHandler(BaseHTTPRequestHandler):
    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self._send(200 if self.path.split("#")[0] in ("/ok", "/page") else 404)

    def do_GET(self):
        if self.path == "/ok":
            self._send(200, b"ok")
        elif self.path == "/page":
            self._send(200, b'<h2 id="intro">Intro</h2>')
        else:
            self._send(404, b"missing")

    def log_message(self, *args):
        pass


class ServerMixin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def base(self):
        return f"http://127.0.0.1:{self.port}"


class TestExtract(unittest.TestCase):
    def test_code_blocks_and_inline_code_are_ignored(self):
        text = (
            "```\n[hidden](gone.md)\n```\n"
            "Real [link](here.md) and `code [fake](gone.md)`\n"
        )
        self.assertEqual(extract_links(text), [(4, "here.md")])

    def test_autolink_found(self):
        self.assertEqual(
            extract_links("see <https://example.com/x> now"),
            [(1, "https://example.com/x")],
        )


class TestLocal(ServerMixin):
    def test_good_file_good_anchor_missing_file_missing_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target.md").write_text("# Getting Started\n\nBody.\n")
            (root / "doc.md").write_text(
                "[ok](target.md) [anchor](target.md#getting-started) "
                "[gone](nope.md) [bad anchor](target.md#nope)\n"
            )
            results = check_files([root / "doc.md"])
            by_url = {r["url"]: r for r in results}
            self.assertEqual(by_url["target.md"]["status"], "OK")
            self.assertEqual(
                by_url["target.md#getting-started"]["status"], "OK"
            )
            self.assertEqual(by_url["nope.md"]["status"], "BROKEN")
            self.assertEqual(by_url["nope.md"]["kind"], "page")
            self.assertEqual(by_url["target.md#nope"]["status"], "BROKEN")
            self.assertEqual(by_url["target.md#nope"]["kind"], "anchor")

    def test_same_page_anchor_and_mailto_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "doc.md"
            source.write_text("# Top\n\n[here](#top) [mail](mailto:a@b.c)\n")
            results = check_files([source])
            by_url = {r["url"]: r for r in results}
            self.assertEqual(by_url["#top"]["status"], "OK")
            self.assertEqual(by_url["mailto:a@b.c"]["status"], "SKIPPED")


class TestRemote(ServerMixin):
    def test_page_ok_page_broken_anchor_ok_anchor_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "doc.md"
            source.write_text("x\n")
            base = self.base()
            self.assertEqual(
                check_link(source, f"{base}/ok", 5)[0], "OK"
            )
            status, kind, _ = check_link(source, f"{base}/missing", 5)
            self.assertEqual((status, kind), ("BROKEN", "page"))
            self.assertEqual(
                check_link(source, f"{base}/page#intro", 5)[0], "OK"
            )
            status, kind, _ = check_link(source, f"{base}/page#gone", 5)
            self.assertEqual((status, kind), ("BROKEN", "anchor"))

    def test_local_only_skips_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "doc.md"
            source.write_text("x\n")
            status, _, _ = check_link(
                source, f"{self.base()}/missing", 5, local_only=True
            )
            self.assertEqual(status, "SKIPPED")


class TestCli(unittest.TestCase):
    def test_exit_zero_when_clean_exit_one_when_broken_json_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.md").write_text("[ok](good.md)\n")
            (root / "bad.md").write_text("[gone](nope.md)\n")
            clean = subprocess.run(
                [sys.executable, str(CLI), str(root / "good.md")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(clean.returncode, 0)
            self.assertIn("1 ok, 0 broken", clean.stdout)
            broken = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--format",
                    "json",
                    str(root / "bad.md"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(broken.returncode, 1)
            data = json.loads(broken.stdout)
            self.assertEqual(data["counts"], {"OK": 0, "BROKEN": 1, "SKIPPED": 0})
            missing = subprocess.run(
                [sys.executable, str(CLI), str(root / "absent")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
