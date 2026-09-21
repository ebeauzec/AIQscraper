"""
test_perf_integration.py - StoragePerf (Plumb) integration: envelope validation,
snapshot storage/retention, and pulling from a (stub) StoragePerf over HTTP with and
without a token.

Stdlib-only. Run via: python tests/run_tests.py
"""

import http.server
import json
import sqlite3
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import perf_integration as pi


def export(arrays=None, **kw):
    d = {"schema": "plumb.aria-export/1", "generated_at": "2026-09-21T08:00:00Z", "plumb_version": "0.21.0",
         "period_hours": 168, "arrays": arrays if arrays is not None else [{"id": "cl01", "name": "cl01", "vendor": "netapp_ontap"}]}
    d.update(kw)
    return d


def new_db():
    db = sqlite3.connect(":memory:")
    pi.init_tables(db)
    return db


class TestValidate(unittest.TestCase):
    def test_accepts_a_valid_export_and_ignores_unknown_fields(self):
        ok, err = pi.validate_export(export(future_field={"x": 1}))
        self.assertTrue(ok, err)

    def test_rejects_things_that_are_not_an_export(self):
        for bad in (None, [], "x", {}, {"schema": "something/else", "arrays": []}, {"schema": "plumb.aria-export/1"}):
            self.assertFalse(pi.validate_export(bad)[0], bad)

    def test_rejects_a_newer_major_schema_with_an_actionable_message(self):
        ok, err = pi.validate_export(export(schema="plumb.aria-export/2"))
        self.assertFalse(ok)
        self.assertIn("major version", err)

    def test_rejects_arrays_without_an_id(self):
        self.assertFalse(pi.validate_export(export(arrays=[{"name": "no id"}]))[0])

    def test_refuses_demo_fleet_data_unless_explicitly_allowed(self):
        ok, err = pi.validate_export(export(mock_data=True))
        self.assertFalse(ok)
        self.assertIn("demo fleet", err)
        self.assertTrue(pi.validate_export(export(mock_data=True), allow_mock=True)[0])


class TestNormalizeUrl(unittest.TestCase):
    def test_strips_trailing_slash_and_api_paths(self):
        self.assertEqual(pi.normalize_base_url("http://plumb.example:8000/"), "http://plumb.example:8000")
        self.assertEqual(pi.normalize_base_url("http://plumb.example:8000/api/aria/export"), "http://plumb.example:8000")

    def test_rejects_non_http_schemes(self):
        for bad in ("", "plumb.example:8000", "file:///etc/passwd", "ftp://x"):
            with self.assertRaises(ValueError):
                pi.normalize_base_url(bad)


class TestStorage(unittest.TestCase):
    def test_store_requires_a_customer(self):
        with self.assertRaises(ValueError):
            pi.store_snapshot(new_db(), export(), "", "import")

    def test_latest_is_newest_per_customer_and_history_is_kept(self):
        db = new_db()
        pi.store_snapshot(db, export(generated_at="2026-09-20T08:00:00Z"), "Acme", "import", filename="a.json")
        pi.store_snapshot(db, export(generated_at="2026-09-21T08:00:00Z"), "Acme", "import", filename="b.json")
        pi.store_snapshot(db, export(generated_at="2026-09-19T08:00:00Z"), "Globex", "import")
        latest = {s["customerName"]: s for s in pi.latest_snapshots(db)}
        self.assertEqual(latest["Acme"]["filename"], "b.json")
        self.assertEqual(latest["Acme"]["payload"]["arrays"][0]["id"], "cl01")
        self.assertEqual(len(pi.list_snapshots(db, "Acme")), 2)

    def test_retention_is_per_customer(self):
        db = new_db()
        for i in range(pi.KEEP_SNAPSHOTS_PER_CUSTOMER + 5):
            pi.store_snapshot(db, export(generated_at="2026-01-01T00:%02d:%02dZ" % (i // 60, i % 60)), "Acme", "import")
        pi.store_snapshot(db, export(), "Globex", "import")
        self.assertEqual(len(pi.list_snapshots(db, "Acme", limit=1000)), pi.KEEP_SNAPSHOTS_PER_CUSTOMER)
        self.assertEqual(len(pi.list_snapshots(db, "Globex")), 1)


class _Stub(http.server.BaseHTTPRequestHandler):
    token = ""
    payload = None
    status_override = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.status_override:
            self.send_response(self.status_override)
            self.end_headers()
            return
        if self.token and self.headers.get("Authorization") != "Bearer " + self.token:
            self.send_response(401)
            self.end_headers()
            return
        if self.path.startswith("/api/aria/info"):
            body = json.dumps({"schema": "plumb.aria-export/1", "plumb_version": "0.21.0", "array_count": 1}).encode()
        elif self.path.startswith("/api/aria/export"):
            body = json.dumps(self.payload or export()).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


class TestPull(unittest.TestCase):
    def setUp(self):
        _Stub.token, _Stub.payload, _Stub.status_override = "", None, None
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), _Stub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.db = new_db()

    def _stop_stub(self):
        if not getattr(self, "_stopped", False):
            self._stopped = True
            self.srv.shutdown()
            self.srv.server_close()

    def tearDown(self):
        self._stop_stub()

    def _source(self, **kw):
        sid = pi.upsert_source(self.db, dict({"customerName": "Acme", "baseUrl": self.url}, **kw))
        return pi.get_source(self.db, sid)

    def test_pull_stores_a_snapshot_and_stamps_the_source(self):
        src = self._source()
        snap = pi.pull_source(self.db, src)
        self.assertTrue(snap)
        self.assertEqual(pi.list_sources(self.db)[0]["lastStatus"], "ok")
        self.assertEqual(pi.latest_snapshots(self.db)[0]["via"], "pull")

    def test_token_is_sent_and_a_wrong_one_is_explained(self):
        _Stub.token = "s3cret"
        with self.assertRaises(ValueError) as cm:
            pi.pull_source(self.db, self._source(token="nope"))
        self.assertIn("token", str(cm.exception).lower())
        self.assertEqual(pi.list_sources(self.db)[0]["lastStatus"], "error")
        self.assertTrue(pi.pull_source(self.db, self._source(token="s3cret")))

    def test_blank_token_on_edit_keeps_the_stored_one(self):
        src = self._source(token="s3cret")
        pi.upsert_source(self.db, {"id": src["id"], "customerName": "Acme", "baseUrl": self.url, "token": ""})
        self.assertEqual(pi.get_source(self.db, src["id"])["token"], "s3cret")

    def test_old_plumb_without_the_endpoint_gets_an_upgrade_hint(self):
        _Stub.status_override = 404
        with self.assertRaises(ValueError) as cm:
            pi.pull_source(self.db, self._source())
        self.assertIn("0.21.0", str(cm.exception))

    def test_unreachable_plumb_is_reported_not_raised_as_a_crash(self):
        src = self._source()
        self._stop_stub()
        with self.assertRaises(ValueError) as cm:
            pi.pull_source(self.db, src)
        self.assertIn("reach", str(cm.exception).lower())

    def test_demo_fleet_export_is_rejected_on_pull(self):
        _Stub.payload = export(mock_data=True)
        with self.assertRaises(ValueError):
            pi.pull_source(self.db, self._source())
        self.assertEqual(pi.latest_snapshots(self.db), [])

    def test_test_source_reports_ok_and_failures(self):
        self.assertTrue(pi.test_source(self.url)["ok"])
        _Stub.token = "s3cret"
        self.assertFalse(pi.test_source(self.url)["ok"])
        self.assertTrue(pi.test_source(self.url, "s3cret")["ok"])

    def test_due_sources_respects_interval_and_enabled(self):
        a = self._source(intervalHours=24)
        self._source(intervalHours=0, label="manual only")
        self._source(enabled=False, label="off")
        self.assertEqual([s["id"] for s in pi.due_sources(self.db)], [a["id"]])
        pi.pull_source(self.db, a)
        self.assertEqual(pi.due_sources(self.db), [])


if __name__ == "__main__":
    unittest.main()
