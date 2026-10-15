# 1.0.0-preview.2 — Windows local preview

Portable Windows x64 program. Extract the entire EP Desktop folder and open EP Desktop.exe. Reviewers do not install Python, packages, or a database.

Built and tested on the standard Windows Server 2022 GitHub runner. The packaged executable self-test, local HTTP service, real Chromium Yes/No saving, boundary drag followed by zoom and further boundary addition, automatic private dataset-profile discovery, and process restart recovery all passed. Browser evidence and SHA256 checksums are attached.

- Automatically recognizes the coordinator's private ep-dataset-profile.json in the selected TDMS root. Rate and evidence source apply only to matching content hashes. The real study profile is not publicly bundled.
- Fixes editable time-range inputs during source loading, which could otherwise be overwritten by the arriving full-waveform range.
- Retains raw-current handling, explicit command-calibration confirmation, immutable local revisions, independent assessments and distinct local/cloud status.

Cloud login and synchronization remain disabled until the separately authorized Supabase setup is completed. This is not a completed cloud collaboration release.

Explorer double-click, SmartScreen and native folder-dialog acceptance remain manual checks. The executable is not code-signed; do not disable security protections if blocked. Original TDMS and earlier annotation archives are not modified.

Verified Windows build: https://github.com/MrWZ93/EP-Detection/actions/runs/38676685892
Runtime source commit: 07fbfb22efa73325953cfc0a58362895d1ad982f

Earlier Mac preview remains available in v1.0.0-preview.1.
