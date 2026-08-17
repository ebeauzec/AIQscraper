# Platform & Data Coverage — Sourcing Traceability

This document tracks which pieces of hardware/firmware/ISL reference data
baked into ARIA's rendering and validation logic are **confirmed against a
primary NetApp source** versus still a **best-effort placeholder**. Adopted
from the sibling NetAppModeler project's `PLATFORM_COVERAGE.md` /
`DATA_SOURCES.md` practice — the goal is that "unverified" is always a
visible, honest state in the code and in this document, never silently
presented as fact.

Where this file says "confirmed," the corresponding code has a comment
citing the same source and date. Where it says "unconfirmed," the code
either labels the UI accordingly (e.g. `"(unverified for this exact model)"`)
or the field is simply not asserted at all.

---

## Backplate rear-panel PCIe slot counts (`app.js`, `_buildControllerBackplate`)

Source: direct fetch of NetApp's own "Key specifications" pages per platform,
2026-08-10 (cross-referenced against a second confirmation pass same day for
FAS8300/FAS8700/FAS9000/C400). PCIe Expansion Slots figures are per NetApp's
published **HA-pair total**; this tool derives per-controller by dividing by
2 (verified consistent against third-party per-controller figures for the
same platforms).

| Platform | Chassis | Internal drive slots | PCIe slots (HA-pair total / per-controller) | Status |
|---|---|---|---|---|
| AFF/ASA A70 | 4U, single-chassis HA | 48 | 18 / 9 | ✅ Confirmed |
| AFF/ASA A90 | 4U, single-chassis HA | 48 | 18 / 9 | ✅ Confirmed |
| AFF/ASA A1K | 2U/controller, dual-chassis HA | 0 (external NS224/NX224 only) | 18 / 9 | ✅ Confirmed |
| AFF/ASA A400 | 4U, single-chassis HA | 0 (external shelf only) | 10 / 5 | ✅ Confirmed |
| AFF/ASA A900 | 8U, single-chassis HA | 0 (external shelf only) | 20 / 10 | ✅ Confirmed |
| AFF/ASA A800 | 4U, single-chassis HA | 48 | 10 / 5 | ✅ Confirmed |
| AFF C800 (EOA) | 4U, single-chassis HA | 48 | 10 / 5 | ✅ Confirmed |
| AFF/ASA C400 | 4U, single-chassis HA | — | 10 / 5 | ✅ Confirmed (matches A400) |
| FAS8300 | — | — | 14 / 7 | ✅ Confirmed |
| FAS8700 | — | — | 14 / 7 | ✅ Confirmed |
| FAS9000 | — | — | 20 / 10 | ⚠️ Confirmed, lower confidence — sourced from a NetApp datasheet PDF, not a live key-specs page (platform predates the current doc format) |
| AFX 1K | 2U/node (A1K-based hardware) | 0 (NX224 external only) | Fixed map: slot 1 = HA replication, slot 7 = cluster replication, slots 10–11 = storage-shelf (NSM140) | ✅ Confirmed (AFX's own hardware-details doc, distinct from plain A1K's slot map) |
| AFF/ASA A20, A30, A50 | — | — | — | ❌ Unconfirmed — falls to generic entry-2U layout, no dedicated slot map |
| AFF/ASA C20, C30, C60 | — | — | — | ❌ Unconfirmed — falls to generic entry-2U layout |
| FAS500f | — | — | — | ❌ Unconfirmed — falls to generic entry-2U layout |
| Most ASA r2 generation | — | — | — | ❌ Unconfirmed — only matched if the platform string literally contains "r2"; real Active IQ naming not verified |
| AFX 2K | 2U/node | — | Same Nexus 9808 switch pairing confirmed (see below); own hardware-details/slot-map page not yet published by NetApp as of last check | ⚠️ Partially confirmed |

**Known gaps to re-check on a future refresh:** AFX 2K's own dedicated
hardware/slot-map page (NetApp had not published one as of the last check —
see `README.md` AFX section); ASA r2's real Active IQ platform-string values
(currently detected only via literal `"r2"` substring match, unconfirmed).

---

## Switch firmware baselines (`data/firmware_baselines.json`, `switches` section)

Source: `docs.netapp.com/us-en/ontap-systems-switches/` + vendor docs, live
harvested by `tools/reference_harvester.py`. **This table is now
auto-synced** — as of the fix in v4.7.0, `reference_harvester.py` propagates
its harvested values from `data/imt_interop.json` into
`data/firmware_baselines.json` every enrichment run, closing the gap where
the two stores could previously drift apart silently. The table below is a
point-in-time snapshot; check the dashboard's Switch Validation tab
(Action Planner → Tab 6) or the live JSON files for the current value.

| Switch | Recommended (as of 2026-08-10) | Confidence |
|---|---|---|
| Cisco NX-OS (Nexus 9000, cluster/MC-IP/AFX) | 10.4.2 | ✅ Confirmed, live-harvested |
| Cisco NX-OS Legacy (Nexus 9336C-FX2, EOA) | 9.3(12) | ✅ Confirmed, live-harvested |
| Cisco MDS 9000 (FC SAN) | 9.2(2) | ✅ Confirmed, live-harvested |
| Brocade FOS | 9.2.1 | ✅ Confirmed, live-harvested |
| Broadcom EFOS (BES-53248, EOA) | 3.12.0.1 | ✅ Confirmed, live-harvested |
| NVIDIA Cumulus (SN2100, EOA) | 5.11.0 | ✅ Confirmed, live-harvested |
| Cisco Nexus 9332D-GX2B / 9364D-GX2A (AFX 1K) | 10.4.2 | ✅ Confirmed, live-harvested |
| Cisco Nexus 9808 (AFX 2K) | 10.6 | ✅ Confirmed (primary-source: NX-OS upgrade procedure page states this pairing explicitly) |

RCF (Reference Configuration File) compliance is tracked as a separate
signal from firmware currency — see `server.py`'s `rcfCompliant` field
(added v4.5.1 follow-up), sourced from Active IQ's own `rcfVersion` field per
switch, not a static baseline.

---

## MetroCluster ISL requirements (`app.js`, `REFERENCE_LIBRARY_MC_REQUIREMENTS`)

| Parameter | Value | Confidence | Source |
|---|---|---|---|
| Max distance — IP | 700 km | ✅ Confirmed, two independent primary sources | NetApp's own ISL requirements page + TR-4705 |
| Max distance — FC (blanket figure) | 300 km | ✅ Confirmed | TR-4705 (blanket figure, not split by switch vendor) |
| Max distance — FC, Brocade-specific | 300 km | ⚠️ Carried forward, not independently reconfirmed | Original TR-4510-era source |
| Max distance — FC, non-Brocade | 200 km | ❌ Unconfirmed | Only found in a community forum thread and an older FC FAQ PDF — NetApp's current guidance is to check the exact figure per switch model via the IMT/Hardware Universe rather than rely on this blanket split |
| Max packet loss (ISL) | ≤0.01% | ✅ Confirmed, reconfirmed 2026-08-10 | NetApp's current ISL requirements page |
| Max jitter (ISL) | ≤3ms round-trip / ≤1.5ms one-way | ✅ Confirmed, reconfirmed 2026-08-10 | NetApp's current ISL requirements page |
| Required MTU (IP backend) | 9216 bytes | ⚠️ Carried forward, not independently reconfirmed against every currently-supported backend switch platform | Original source |

**No live ISL telemetry exists in the Active IQ GraphQL schema** — confirmed
by a full schema sweep of all 518 types (2026-08-10): no packet-loss/
jitter/distance field is exposed anywhere reachable from a `Switch` or
`Cluster` type. The numbers above will always be static reference values
displayed as guidance text, never a live measurement, unless NetApp adds
such a field to the API. `mcContext` (added v4.7.0) flags which harvested
switches sit on a MetroCluster ISL, sourced from the confirmed-real
per-system `isMetroCluster` field — this identifies *which* switches the
static guidance applies to, not a live reading of the ISL's actual health.

---

## E-Series / SANtricity per-port telemetry

**Confirmed absent from the Active IQ schema, not a harvest bug.** A full
sweep of all 518 GraphQL types (2026-08-10) found `networkPorts`,
`portInterface`, and `adapterInterface` exist as fields on exactly three
types: `ONTAPSystem`, `CloudVolumeONTAP`, and `ONTAPSystemInterface`. They do
not exist on `SantricitySystem` or anything reachable from it. SANtricity's
own host-port/HIC configuration is presumably exposed through SANtricity's
own management API (Web Services API / SANtricity System Manager), a
separate integration this tool does not currently have — see `README.md`'s
architecture notes for the current single-integration (Active IQ only)
scope.

---

## How to keep this file honest

- When a platform/switch/ISL figure is verified or corrected, update the
  table row **and** the corresponding in-code comment in the same commit —
  they should never drift apart.
- Never upgrade a row from ⚠️/❌ to ✅ without a specific primary-source
  citation (a docs.netapp.com URL, a TR number, or a live API response) —
  "it looks right" or "it matches the old placeholder" is not a
  confirmation.
- `tools/reference_harvester.py` re-harvests switch firmware data on its own
  schedule; this file's switch table should be treated as a snapshot, not
  re-verified by hand each time — check the live JSON files for current
  values before assuming this table is stale.

---

*Last updated: 2026-08-17*
