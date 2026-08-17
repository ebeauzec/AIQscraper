"""
test_asup_parser.py - Regression suite for tools/asup_parser.py
=================================================================
Stdlib-only (unittest), matching the "no pip packages required" philosophy
already established for this project (see README.md). Run with:

    python tests/test_asup_parser.py

This is the first automated test suite in this codebase -- adopted from
NetAppModeler's tests/run_tests.py practice (a sibling project) of pinning
real-bug fixes as regression assertions rather than relying solely on manual
live-browser verification. Each parser test below targets one of the four
ASUP-format enhancements ported from NetAppModeler's parser.js this session:
licenses.xml, aggr-info.xml, SAS Host Adapter port lines, and the
storage-shelf.xml/STORAGE-SHELF.txt cross-reference.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import asup_parser as ap


class TestLicensesXml(unittest.TestCase):
    def test_active_license_recognized(self):
        xml = b"""
        <results>
          <asup:ROW xmlns:asup="x">
            <package>NFS</package>
            <type>license</type>
          </asup:ROW>
        </results>
        """
        out = ap._parse_licenses_xml(xml)
        self.assertIsNotNone(out)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["package"], "NFS")
        self.assertEqual(out[0]["status"], "active")

    def test_expired_demo_license(self):
        xml = b"""
        <asup:ROW xmlns:asup="x">
          <package>FlexClone</package>
          <type>demo</type>
          <entitlement-info>{&quot;expires&quot;:&quot;2018-01-01&quot;}</entitlement-info>
        </asup:ROW>
        """
        out = ap._parse_licenses_xml(xml)
        self.assertIsNotNone(out)
        self.assertEqual(out[0]["package"], "FlexClone")
        self.assertEqual(out[0]["status"], "expired")
        self.assertIn("2018-01-01", out[0]["details"])

    def test_active_demo_license_not_yet_expired(self):
        xml = b"""
        <asup:ROW xmlns:asup="x">
          <package>SnapMirror</package>
          <type>demo</type>
          <entitlement-info>{&quot;expires&quot;:&quot;2099-01-01&quot;}</entitlement-info>
        </asup:ROW>
        """
        out = ap._parse_licenses_xml(xml)
        self.assertEqual(out[0]["status"], "active")

    def test_unrecognized_package_skipped(self):
        # "SnapRestore" is a real license package but not one this system's UI
        # tracks (see _LICENSE_PACKAGE_NAMES) -- must not error, just be omitted.
        xml = b"""
        <asup:ROW xmlns:asup="x"><package>SnapRestore</package><type>license</type></asup:ROW>
        """
        out = ap._parse_licenses_xml(xml)
        self.assertIsNone(out)

    def test_multiple_rows_dedup_by_package(self):
        # Two rows for the same package (e.g. cluster + node-scoped duplicate) --
        # the later row's status should win, not produce two entries.
        xml = b"""
        <asup:ROW xmlns:asup="x"><package>CIFS</package><type>license</type></asup:ROW>
        <asup:ROW xmlns:asup="x"><package>CIFS</package><type>license</type></asup:ROW>
        """
        out = ap._parse_licenses_xml(xml)
        self.assertEqual(len(out), 1)

    def test_no_rows_returns_none(self):
        self.assertIsNone(ap._parse_licenses_xml(b"<results></results>"))
        self.assertIsNone(ap._parse_licenses_xml(b""))
        self.assertIsNone(ap._parse_licenses_xml(None))


class TestAggrInfoXml(unittest.TestCase):
    def test_capacity_parsed_in_bytes_to_kib(self):
        xml = b"""
        <asup:ROW xmlns:asup="x">
          <name>aggr1</name>
          <size>1073741824</size>
          <available_size>536870912</available_size>
          <usedsize>536870912</usedsize>
        </asup:ROW>
        """
        out = ap._parse_aggr_info_xml(xml)
        self.assertIsNotNone(out)
        self.assertIn("aggr1", out)
        self.assertAlmostEqual(out["aggr1"]["totalKiB"], 1073741824 / 1024)
        self.assertAlmostEqual(out["aggr1"]["usedKiB"], 536870912 / 1024)
        self.assertAlmostEqual(out["aggr1"]["availKiB"], 536870912 / 1024)

    def test_size_equals_used_plus_available_real_data_invariant(self):
        # Ported comment says size == available_size + usedsize was verified
        # byte-for-byte against real data -- assert the fixture itself upholds
        # that invariant so a future edit can't silently break the assumption.
        xml = b"""
        <asup:ROW xmlns:asup="x">
          <name>aggr0</name><size>300</size><available_size>100</available_size><usedsize>200</usedsize>
        </asup:ROW>
        """
        out = ap._parse_aggr_info_xml(xml)
        row = out["aggr0"]
        self.assertAlmostEqual(row["totalKiB"], row["usedKiB"] + row["availKiB"])

    def test_incomplete_row_skipped(self):
        xml = b"""<asup:ROW xmlns:asup="x"><name>aggr2</name><size>100</size></asup:ROW>"""
        out = ap._parse_aggr_info_xml(xml)
        self.assertIsNone(out)

    def test_no_data_returns_none(self):
        self.assertIsNone(ap._parse_aggr_info_xml(b""))


class TestSasHostAdapters(unittest.TestCase):
    def test_up_and_down_adapters_parsed(self):
        text = (
            b"slot 0: SAS Host Adapter 0a (PMC-Sierra PM8001 rev. C, SAS, <UP>)\n"
            b"slot 0: SAS Host Adapter 0b (PMC-Sierra PM8001 rev. C, SAS, <DOWN>)\n"
        )
        out = ap._parse_sas_host_adapters(text)
        self.assertIsNotNone(out)
        self.assertEqual(len(out), 2)
        names = {p["name"]: p["status"] for p in out}
        self.assertEqual(names["0a"], "up")
        self.assertEqual(names["0b"], "down")

    def test_far_apart_matches_still_found(self):
        # Real bundles can spread ~41,000 chars of verbose per-disk detail between
        # adapter lines -- a windowed/bounded regex would miss the second one.
        filler = b"x" * 45000
        text = b"SAS Host Adapter 0a (foo, SAS, <UP>)\n" + filler + b"\nSAS Host Adapter 0c (foo, SAS, <UP>)\n"
        out = ap._parse_sas_host_adapters(text)
        self.assertEqual(len(out), 2)

    def test_duplicate_adapter_names_deduped_case_insensitive(self):
        text = b"SAS Host Adapter 0a (x, SAS, <UP>)\nSAS Host Adapter 0A (x, SAS, <UP>)\n"
        out = ap._parse_sas_host_adapters(text)
        self.assertEqual(len(out), 1)

    def test_no_adapters_returns_none(self):
        self.assertIsNone(ap._parse_sas_host_adapters(b"nothing relevant here"))


class TestShelves(unittest.TestCase):
    def test_shelf_resolved_via_product_id_cross_reference(self):
        combined = (
            b"<product_id>DS212-12</product_id><serial_number>SHFHU2003000319</serial_number>\n"
            b"Shelf name: shelf1\n"
            b"Shelf id: 3\n"
            b"...junk...\n"
            b"Shelf S/N: SHFHU2003000319\n"
        )
        out = ap._parse_shelves(combined, combined)
        self.assertIsNotNone(out)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "3")
        self.assertEqual(out[0]["serialNumber"], "SHFHU2003000319")
        # "DS212-12" strips the trailing generation number to "DS212", a known model
        self.assertEqual(out[0]["model"], "DS212")

    def test_model_with_c_suffix_resolved(self):
        combined = (
            b"<product_id>DS460-12</product_id><serial_number>SN1</serial_number>\n"
            b"Shelf name: s\nShelf id: 1\nx\nShelf S/N: SN1\n"
        )
        out = ap._parse_shelves(combined, combined)
        # "DS460" alone isn't in the catalog, but "DS460C" is -- must resolve to that
        self.assertEqual(out[0]["model"], "DS460C")

    def test_no_product_id_match_falls_back_to_unknown(self):
        combined = b"Shelf name: s\nShelf id: 2\nx\nShelf S/N: SN2\n"
        out = ap._parse_shelves(combined, combined)
        self.assertEqual(out[0]["model"], "Unknown")

    def test_same_shelf_from_both_iom_modules_deduped(self):
        combined = (
            b"<product_id>DS212C</product_id><serial_number>SN9</serial_number>\n"
            b"Shelf name: s\nShelf id: 5\nx\nShelf S/N: SN9\n"
            b"Shelf name: s\nShelf id: 5\nx\nShelf S/N: SN9\n"  # same shelf, other IOM
        )
        out = ap._parse_shelves(combined, combined)
        self.assertEqual(len(out), 1)

    def test_empty_input_returns_none(self):
        self.assertIsNone(ap._parse_shelves(b"", b""))
        self.assertIsNone(ap._parse_shelves(None, None))


class TestAggrInfoOverridesAggrStatus(unittest.TestCase):
    """_build_system_dict should let aggr-info.xml's byte-accurate capacity
    override/fill in aggr-status-r's text-parsed capacity by aggregate name --
    this is the exact real-bundle scenario the port fixes (aggr status -r with
    RAID/disk membership only, no capacity numbers at all)."""

    def test_capacity_filled_in_when_aggr_status_has_none(self):
        aggrs = [{"name": "aggr1", "state": "online", "totalKiB": 0, "usedKiB": 0, "availKiB": 0}]
        aggr_info = {"aggr1": {"totalKiB": 1000.0, "usedKiB": 400.0, "availKiB": 600.0}}
        system = ap._build_system_dict(
            cluster={"clusterName": "c1", "serialNumber": "S1", "nodeCount": 1},
            sysconfig={"platform": "FAS8040"}, aggrs=aggrs, df_info=None, snapmirrors=None,
            asup_info=None, ha_config=None, customer_name="Cust", product_hint="ontap",
            sg_info=None, eseries_info=None, version_str="9.10.1",
            aggr_info_capacity=aggr_info,
        )
        self.assertAlmostEqual(system["clusterPhysicalUsedTB"], ap._kib_to_tb(400.0))

    def test_licenses_and_shelves_and_ports_populate_system_dict(self):
        system = ap._build_system_dict(
            cluster={"clusterName": "c1", "serialNumber": "S1", "nodeCount": 1},
            sysconfig={"platform": "FAS8040"}, aggrs=None, df_info=None, snapmirrors=None,
            asup_info=None, ha_config=None, customer_name="Cust", product_hint="ontap",
            sg_info=None, eseries_info=None, version_str="9.10.1",
            licenses=[{"package": "NFS", "status": "active", "details": ""}],
            shelves=[{"id": "1", "model": "DS212C", "serialNumber": "SN1"}],
            sas_ports=[{"name": "0a", "status": "up"}],
        )
        self.assertEqual(system["licenses"], [{"package": "NFS", "status": "active", "details": ""}])
        self.assertEqual(system["shelves"][0]["model"], "DS212C")
        self.assertEqual(system["storagePorts"][0]["name"], "0a")

    def test_defaults_stay_empty_lists_not_none(self):
        # Every existing caller of _build_system_dict (real parse_bundle path with
        # no licenses/shelves/ports found) must keep getting [] not None -- app.js
        # and other consumers iterate these fields unconditionally.
        system = ap._build_system_dict(
            cluster=None, sysconfig=None, aggrs=None, df_info=None, snapmirrors=None,
            asup_info=None, ha_config=None, customer_name="Cust", product_hint="ontap",
            sg_info=None, eseries_info=None, version_str=None,
        )
        self.assertEqual(system["licenses"], [])
        self.assertEqual(system["shelves"], [])
        self.assertEqual(system["storagePorts"], [])


class TestParseBundleEndToEnd(unittest.TestCase):
    """Exercises parse_bundle() the same way the app actually calls it --
    building a minimal in-memory bundle rather than only unit-testing the
    inner parser functions in isolation."""

    def test_plain_xml_bundle_with_cluster_info(self):
        xml = b"""<?xml version="1.0"?>
        <results>
          <cluster-name>test-cluster</cluster-name>
          <system-serial-number>ABC123</system-serial-number>
          <version>9.12.1</version>
        </results>
        """
        result = ap.parse_bundle("asup.xml", xml, customer_name="Test Customer")
        self.assertTrue(result["ok"])
        self.assertIsNotNone(result["system"])
        self.assertEqual(result["system"]["customerName"], "Test Customer")
        self.assertIn("licenses", result["system"])
        self.assertIn("storagePorts", result["system"])

    def test_unsupported_format_returns_error(self):
        result = ap.parse_bundle("bundle.rar", b"not a real archive", customer_name="")
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["error"])

    def test_coverage_reports_new_sections(self):
        xml = b"""<?xml version="1.0"?><results><cluster-name>c</cluster-name></results>"""
        result = ap.parse_bundle("asup.xml", xml)
        labels = {s["label"] for s in result["coverage"]["sections"]}
        self.assertIn("Software Licenses", labels)
        self.assertIn("Disk Shelf Inventory", labels)
        self.assertIn("SAS Storage Ports", labels)


if __name__ == "__main__":
    unittest.main(verbosity=2)
