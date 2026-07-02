---
name: source-archive
description: Fingerprint and archive source Wind Excel files before any strategy logic runs.
when_to_use: Use at the beginning of each daily workflow to create source-data traceability.
inputs:
  - etf_file
  - tl_file
  - cb_file
outputs:
  - source_manifest
  - source_manifest_path
---

This skill creates a deterministic manifest for all configured source Excel files.
It copies existing files into a run-specific archive folder and never modifies the
customer's original workbooks.
