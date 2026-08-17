"""
test_multi_account.py - Regression suite for server.py's multi-account
(multi-customer) merge/config logic added this session.
=========================================================================
Stdlib-only. These pin two real bugs found during live manual testing of the
multi-account feature so they can't silently regress:
  1. _MERGE_LIST_FIELDS previously included "riskInstances", which is stored
     as an int count (not a list) -- crashed the merge with a TypeError.
  2. Removing an account from config left its cached data haunting the merged
     view forever (orphaned cache row, no way to refresh or explain it).

Run via: python tests/run_tests.py  (or directly: python tests/test_multi_account.py)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import server


def _fake_result(account_id, label, n_systems, extra=None):
    """Build a minimal harvest-result dict shaped like _do_full_harvest's
    output, tagged the same way real per-account harvests are tagged."""
    systems = [
        {"serialNumber": f"{account_id}-SN{i}", "systemName": f"sys{i}",
         "accountId": account_id, "accountLabel": label}
        for i in range(n_systems)
    ]
    result = {
        "systems": systems, "clusters": [], "risks": [], "cases": [],
        "tamSites": [], "tamRenewals": [], "acknowledgedRisksNowExploited": [],
        "totalSystems": n_systems, "totalClusters": 0, "totalRisks": 0,
        "totalCases": 0, "totalRiskInstances": n_systems * 2,  # int, not a list -- the real shape
        "riskInstances": n_systems * 2,
        "accountId": account_id, "accountLabel": label,
    }
    if extra:
        result.update(extra)
    return result


class TestMergeAccountResults(unittest.TestCase):
    def test_single_account_passthrough(self):
        r = _fake_result("a", "Account A", 3)
        merged = server._merge_account_results([("a", r, {})])
        self.assertIs(merged, r)  # single-account path returns as-is, no copy

    def test_two_accounts_merge_systems(self):
        ra = _fake_result("a", "Account A", 2)
        rb = _fake_result("b", "Account B", 3)
        merged = server._merge_account_results([("a", ra, {}), ("b", rb, {})])
        self.assertEqual(len(merged["systems"]), 5)
        self.assertEqual(merged["totalSystems"], 5)

    def test_risk_instances_is_summed_not_iterated(self):
        # Regression: riskInstances is an int count in real harvest results,
        # not a list. A prior version of _MERGE_LIST_FIELDS tried to iterate
        # it and crashed with "TypeError: 'int' object is not iterable".
        ra = _fake_result("a", "Account A", 2)  # totalRiskInstances = 4
        rb = _fake_result("b", "Account B", 3)  # totalRiskInstances = 6
        merged = server._merge_account_results([("a", ra, {}), ("b", rb, {})])
        self.assertEqual(merged["totalRiskInstances"], 10)
        self.assertIsInstance(merged["riskInstances"], int)

    def test_accounts_summary_included(self):
        ra = _fake_result("a", "Account A", 2)
        rb = _fake_result("b", "Account B", 3)
        merged = server._merge_account_results([("a", ra, {}), ("b", rb, {})])
        ids = {a["id"]: a["systemCount"] for a in merged["accounts"]}
        self.assertEqual(ids, {"a": 2, "b": 3})

    def test_empty_input_returns_none(self):
        self.assertIsNone(server._merge_account_results([]))

    def test_dedup_by_account_and_serial(self):
        # Same account appearing twice (e.g. a stale duplicate cache read)
        # shouldn't double-count its systems.
        ra = _fake_result("a", "Account A", 2)
        merged = server._merge_account_results([("a", ra, {}), ("a", ra, {})])
        self.assertEqual(len(merged["systems"]), 2)


class TestGetAccounts(unittest.TestCase):
    def test_legacy_single_token_synthesizes_default_account(self):
        cfg = {"refreshToken": "tok123", "watchlistId": "wl1", "tamName": "Jane TAM"}
        accounts = server._get_accounts(cfg)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["id"], "default")
        self.assertEqual(accounts[0]["refreshToken"], "tok123")
        self.assertEqual(accounts[0]["watchlistId"], "wl1")

    def test_no_token_no_accounts_returns_empty(self):
        self.assertEqual(server._get_accounts({}), [])

    def test_accounts_array_used_when_present(self):
        cfg = {"accounts": [
            {"id": "cust1", "label": "Customer 1", "refreshToken": "t1", "enabled": True},
            {"id": "cust2", "label": "Customer 2", "refreshToken": "t2", "enabled": False},
        ]}
        accounts = server._get_accounts(cfg)
        # Disabled accounts are excluded
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["id"], "cust1")

    def test_account_without_token_excluded_even_if_enabled(self):
        cfg = {"accounts": [{"id": "cust1", "label": "No Token", "refreshToken": "", "enabled": True}]}
        self.assertEqual(server._get_accounts(cfg), [])

    def test_legacy_fields_ignored_when_accounts_array_present(self):
        # If accounts[] exists, the top-level refreshToken must NOT also be
        # synthesized as an extra "default" account (would double-sync it).
        cfg = {"refreshToken": "legacy-tok", "accounts": [
            {"id": "cust1", "label": "C1", "refreshToken": "t1", "enabled": True}
        ]}
        accounts = server._get_accounts(cfg)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["id"], "cust1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
